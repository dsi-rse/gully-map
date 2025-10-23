import glob
import threading
import queue

import numpy as np
import rasterio.warp

NUM_THREADS = 4  # limited by RAM

NODATA = np.finfo(np.float32).max
FEET_PER_METER = 3.2808398950131

print("reading 2022 file")
with rasterio.open("SONOMA_DTM_2020.tif") as src:
    src_crs = src.crs
    src_transform = src.transform
    src_width = src.width
    src_height = src.height
    src_bounds = src.bounds

dst_crs = "EPSG:3857"

dst_transform, dst_width, dst_height = rasterio.warp.calculate_default_transform(
    src_crs, dst_crs, src_width, src_height, *src_bounds
)

scratch = []
for i in range(NUM_THREADS):
    print(f"allocating array {i + 1} of {NUM_THREADS}")
    scratch.append(np.full((dst_height, dst_width), NODATA, dtype=np.float32))

filenames = sorted(glob.glob("bare-earth-hydroflattened-2013/*.tif"))

tasks = queue.Queue()
for fileindex, filename in enumerate(filenames):
    tasks.put((fileindex, filename))

for _ in range(NUM_THREADS):
    tasks.put(None)

def worker(index):
    while True:
        task = tasks.get()
        if task is None:
            break

        fileindex, filename = task
        print(f"worker {index} takes {fileindex + 1} of {len(filenames)}: {filename}")

        with rasterio.open(filename) as file:
            file_data = file.read(1) / FEET_PER_METER
            file_transform = file.transform
            file_crs = file.crs
            file_nodata = file.nodata

        rasterio.warp.reproject(
            source=file_data,
            destination=scratch[index],
            src_transform=file_transform,
            src_crs=file_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=rasterio.enums.Resampling.bilinear,
            src_nodata=file_nodata,
            dst_nodata=NODATA,
            init_dest_nodata=True,
        )

        del file_data

    print(f"worker {index} is done")

threads = [threading.Thread(target=worker, args=(i,)) for i in range(NUM_THREADS)]

for thread in threads:
    thread.start()

for thread in threads:
    thread.join()

print("combining scratch spaces")
tmp_data = scratch[0]
for i, array in enumerate(scratch[1:]):
    selection = (array != NODATA)
    print(f"    {i + 1} into 0; selection has {np.count_nonzero(selection)} pixels")
    tmp_data[selection] = array[selection]

del scratch

print(f"{np.count_nonzero(tmp_data != NODATA) = } pixels")

dst_data = tmp_data.view(np.uint8).reshape((dst_height, dst_width, 4))
dst_data = np.transpose(dst_data, (2, 0, 1))
del tmp_data

print("writing")
with rasterio.open(
    "elevation-2013.tif",
    "w",
    driver="GTiff",
    crs=dst_crs,
    transform=dst_transform,
    width=dst_width,
    height=dst_height,
    count=4,
    dtype="uint8",
    compress="DEFLATE",
    tiled=True,
    bigtiff="YES",
) as dst:
    dst.write(dst_data, [1, 2, 3, 4])

print("done")
