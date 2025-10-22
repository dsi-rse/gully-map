import numpy as np
import rasterio.warp

print("reading")
with rasterio.open("SONOMA_DTM_2020.tif") as src:
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
tmp_data = np.empty((dst_height, dst_width), dtype=np.float32)
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

dst_data = tmp_data.view(np.uint8).reshape((dst_height, dst_width, 4))
dst_data = np.transpose(dst_data, (2, 0, 1))
del tmp_data

print("writing")
with rasterio.open(
    "elevation-2022.tif",
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
