import numpy as np
import rasterio.warp

NODATA = np.finfo(np.float32).max
FEET_PER_METER = 3.2808398950131

# gdal_merge.py -o merged_2013.tif -of GTiff -n -9999 -a_nodata -9999 bare-earth-hydroflattened-2013/*.tif

print("reading")
with rasterio.open("merged_2013.tif") as src:
    src_data = src.read(1)
    src_crs = src.crs
    src_transform = src.transform
    src_width = src.width
    src_height = src.height
    src_bounds = src.bounds

print(f"{np.count_nonzero(src_data == -9999) = } and {src_data.size = }")

dst_crs = "EPSG:3857"

dst_transform, dst_width, dst_height = rasterio.warp.calculate_default_transform(
    src_crs, dst_crs, src_width, src_height, *src_bounds
)

print("reprojecting")
tmp_data = np.empty((dst_height, dst_width), dtype=np.float32)
rasterio.warp.reproject(
    source=src_data,
    destination=tmp_data,
    src_transform=src_transform,
    src_crs=src_crs,
    dst_transform=dst_transform,
    dst_crs=dst_crs,
    resampling=rasterio.enums.Resampling.bilinear,
    src_nodata=-9999,
    dst_nodata=NODATA,
)
del src_data

print("converting from feet into meters")
tmp_data[tmp_data != NODATA] /= FEET_PER_METER

print(f"{np.count_nonzero(tmp_data == NODATA) = } and {tmp_data.size = }")

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

# rio pmtiles elevation-2013.tif elevation-2013.pmtiles --format PNG --zoom-levels 17..17 --tile-size 256
