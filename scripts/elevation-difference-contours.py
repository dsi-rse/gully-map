import numpy as np
import geopandas as gpd
import rasterio
import scipy.ndimage
import skimage
import shapely

print("reading elevation-2022")
with rasterio.open("elevation-2022.tif") as file:
    elevation2022 = file.read(1)
    elevation2022[elevation2022 > 1e30] = np.nan
    transform = file.transform
    crs = file.crs

print("reading and reprojecting elevation-2013")
with rasterio.open("elevation-2013.tif") as file:
    tmp_original = file.read(1)
    elevation2013 = np.full(elevation2022.shape, np.nan, dtype=tmp_original.dtype)
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

print("computing difference")
difference = elevation2022 - elevation2013
del elevation2013
del elevation2022

print("capping differences at +-30 meters")
np.minimum(difference, 30, out=difference)
np.maximum(difference, -30, out=difference)

print("blurring differences for smooth contours")
difference = scipy.ndimage.gaussian_filter(difference, 10)

print("computing contours")
df_level = []
df_geometry = []
for level in [-3, -2, -1, 1, 2, 3]:
    print(f"    level {level}")
    contours = skimage.measure.find_contours(difference, level)
    for contour in contours:
        xs, ys = rasterio.transform.xy(transform, contour[:, 0], contour[:, 1])
        df_level.append(level)
        df_geometry.append(shapely.geometry.LineString(zip(xs, ys)))

print("creating DataFrame")
df = gpd.DataFrame({"level": df_level}, geometry=df_geometry, crs=crs)
df.to_crs("EPSG:4326", inplace=True)

print("writing GeoJSON")
df.to_file("elevation-difference-contours.geojson")
