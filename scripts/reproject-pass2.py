import numpy as np
import rasterio.warp

# gdal_merge.py -o merged_pass2.tif -of GTiff -n nan -a_nodata 0 gully-pass2/*.tif

print("reading")
with rasterio.open("merged_pass2.tif") as src:
    src_data = src.read(1)
    src_crs = src.crs
    src_transform = src.transform
    src_width = src.width
    src_height = src.height
    src_bounds = src.bounds

dst_crs = "EPSG:3857"

dst_transform, dst_width, dst_height = rasterio.warp.calculate_default_transform(
    src_crs, dst_crs, src_width, src_height, *src_bounds
)

print("reprojecting")
tmp_data = np.zeros((dst_height, dst_width), dtype=np.float32)
rasterio.warp.reproject(
    source=src_data,
    destination=tmp_data,
    src_transform=src_transform,
    src_crs=src_crs,
    dst_transform=dst_transform,
    dst_crs=dst_crs,
    resampling=rasterio.enums.Resampling.bilinear,
)
del src_data

print("preparing output array")
dst_data = np.zeros((4, dst_height, dst_width), dtype=np.uint8)
dst_data[0] = 148
dst_data[1] = 181
dst_data[2] = 255
dst_data[3] = np.maximum(0, np.minimum(1, tmp_data) * 255)
del tmp_data

print("writing")
with rasterio.open(
    "gully-detection-pass2.tif",
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

# rio pmtiles gully-detection-pass2.tif gully-detection-pass2.pmtiles --format PNG --tile-size 512
