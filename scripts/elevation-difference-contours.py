import time

import numpy as np
import geopandas as gpd
import rasterio.warp
import scipy.ndimage
import skimage
import shapely

starttime = time.time()

print(int(time.time() - starttime), "reading elevation-2022", flush=True)
with rasterio.open("elevation-2022.tif") as file:
    print(int(time.time() - starttime), "    reading", flush=True)
    elevation2022 = file.read([1, 2, 3, 4])
    print(int(time.time() - starttime), "    converting to a floating point array", flush=True)
    elevation2022 = np.ascontiguousarray(np.transpose(elevation2022, [1, 2, 0])).view(np.float32)[:, :, 0]
    print(int(time.time() - starttime), "    setting nodata values to nan", flush=True)
    elevation2022[elevation2022 > 1e30] = np.nan
    transform = file.transform
    crs = file.crs

print(int(time.time() - starttime), "writing elevation-2022 as a floating-point GeoTIFF", flush=True)
with rasterio.open(
    "elevation-2022-float.tif",
    "w",
    driver="GTiff",
    count=1,
    transform=transform,
    crs=crs,
    height=elevation2022.shape[0],
    width=elevation2022.shape[1],
    dtype=np.float32,
    nodata=np.nan,
    compress="LZW",
    tiled=True,
    blockxsize=1024,
    blockysize=1024,
    bigtiff="YES",
) as file:
    file.write(elevation2022, 1)

print(int(time.time() - starttime), "reading and reprojecting elevation-2013", flush=True)
with rasterio.open("elevation-2013.tif") as file:
    print(int(time.time() - starttime), "    reading", flush=True)
    tmp_original = file.read([1, 2, 3, 4])
    print(int(time.time() - starttime), "    converting to a floating point array", flush=True)
    tmp_original = np.ascontiguousarray(np.transpose(tmp_original, [1, 2, 0])).view(np.float32)[:, :, 0]
    print(int(time.time() - starttime), "    setting nodata values to nan", flush=True)
    tmp_original[tmp_original > 1e30] = np.nan
    print(int(time.time() - starttime), "    allocating output array", flush=True)
    elevation2013 = np.full(elevation2022.shape, np.nan, dtype=tmp_original.dtype)
    print(int(time.time() - starttime), "    reprojecting", flush=True)
    rasterio.warp.reproject(
        source=tmp_original,
        destination=elevation2013,
        src_transform=file.transform,
        dst_transform=transform,
        src_crs=file.crs,
        dst_crs=crs,
        resampling=rasterio.warp.Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    del tmp_original

print(int(time.time() - starttime), "writing elevation-2013 as a floating-point GeoTIFF", flush=True)
with rasterio.open(
    "elevation-2013-float.tif",
    "w",
    driver="GTiff",
    count=1,
    transform=transform,
    crs=crs,
    height=elevation2013.shape[0],
    width=elevation2013.shape[1],
    dtype=np.float32,
    nodata=np.nan,
    compress="LZW",
    tiled=True,
    blockxsize=1024,
    blockysize=1024,
    bigtiff="YES",
) as file:
    file.write(elevation2013, 1)

print(int(time.time() - starttime), "computing difference", flush=True)
difference = elevation2022 - elevation2013

print(int(time.time() - starttime), "capping differences at +-30 meters", flush=True)
np.minimum(difference, 30, out=difference)
np.maximum(difference, -30, out=difference)

print(int(time.time() - starttime), "blurring differences for smooth contours", flush=True)
difference = scipy.ndimage.gaussian_filter(difference, 10)

print(int(time.time() - starttime), "computing contours", flush=True)
df_level = []
df_geometry = []
for level in [-3, -2, -1, 1, 2, 3]:
    print(int(time.time() - starttime), f"    level {level}", flush=True)
    contours = skimage.measure.find_contours(difference, level)
    for contour in contours:
        xs, ys = rasterio.transform.xy(transform, contour[:, 0], contour[:, 1])
        df_level.append(level)
        df_geometry.append(shapely.geometry.LineString(zip(xs, ys)))

print(int(time.time() - starttime), "creating DataFrame", flush=True)
df = gpd.GeoDataFrame({"level": df_level}, geometry=df_geometry, crs=crs)
df.to_crs("EPSG:4326", inplace=True)

print(int(time.time() - starttime), "writing GeoJSON", flush=True)
df.to_file("elevation-difference-contours.geojson")
