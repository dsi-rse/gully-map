# Data products

The data presented on the web app can be accessed directly, for instance as tiles in QGIS or ArcGIS. All data products are in the UChicago DSI `gully-map` R2 bucket on CloudFlare, with world-readable permissions. Most of them have been formatted as PMTiles (raster or vector) so that they can be accessed remotely without downloading them.

If your version of QGIS and ArcGIS has built-in PMTiles support, just point it at the R2 URL (the ones below that start with `https://gully-map.cdn.uchicago-dsi.org/`). If you don't have this feature, you can access the data through a local [tileserver-gl](https://tileserver.readthedocs.io/), either by installing it or running its Docker image:

```
docker run --rm -it -v $(pwd):/data -p 8080:8080 maptiler/tileserver-gl:latest
```

in a directory (`$(pwd)`) containing this file: [config.json](config.json). This file points to all of the R2 URLs so that the local tileserver-gl can pass them to QGIS/ArcGIS as a tile service, with a URL containing `{z}/{x}/{y}`. You can add raster layers to a QGIS/ArcGIS project with

* Layer > Add Layer > Add XYZ Layer...

and you can add vector layers with

* Layer > Add Layer > Add Vector Tile Layer...

## sonoma-county-parcels

On the map as the "Land ownership boundaries" checkbox, included so that we can find out who to contact about a particular gully. It was minimally transformed from the source data on [Sonoma County GIS](https://gis.sonomacounty.ca.gov/pages/data). We converted from Shapefile to PMTiles, projected to EPSG:3857, renamed and dropped fields.

* [https://gully-map.cdn.uchicago-dsi.org/sonoma-county-parcels.pmtiles](https://gully-map.cdn.uchicago-dsi.org/sonoma-county-parcels.pmtiles) (26.5 MiB)
* `http://localhost:8080/data/sonoma-county-parcels/{z}/{x}/{y}.pbf`
* format: PBF
* zoom: 0..14
* bounds: -123.532896, 38.11246, -122.350206, 38.8527739
* layer: `parcels`
* fields: `parcel`, `type`, `description`, `address`, `city`
* original source: https://gis.sonomacounty.ca.gov/maps/4b231e8ffbac47abb9a78296e550ffa1 (Shapefile)

<img src="README-img/sonoma-county-parcels.png" width="400">

## sonoma-county-ladder-fuels-4m and 8m

On the map as the "Fire hazard" group of radio buttons, these were minimally transformed from the source on [SonomaVegMap](https://sonomavegmap.org/), where it is one of the provided 2022 LIDAR products. We converted from GeoTIFF to PMTiles, projected to EPSG:3857, and colored red (scaled float32 to the red and alpha channels).

* [https://gully-map.cdn.uchicago-dsi.org/sonoma-county-ladder-fuels-4m.pmtiles](https://gully-map.cdn.uchicago-dsi.org/sonoma-county-ladder-fuels-4m.pmtiles) (54.3 MiB)
* [https://gully-map.cdn.uchicago-dsi.org/sonoma-county-ladder-fuels-8m.pmtiles](https://gully-map.cdn.uchicago-dsi.org/sonoma-county-ladder-fuels-8m.pmtiles) (60.8 MiB)
* `http://localhost:8080/data/sonoma-county-ladder-fuels-4m/{z}/{x}/{y}.webp`
* `http://localhost:8080/data/sonoma-county-ladder-fuels-8m/{z}/{x}/{y}.webp`
* format: WEBP
* tile size: 512
* zoom: 0..13
* bounds (4m): -123.5532079, 38.1057112, -122.3286212, 38.8578298
* bounds (8m): -123.5532079, 38.1057112, -122.3286212, 38.8578298
* original source: [https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_lf_4.tif](https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_lf_4.tif) and [https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_lf_8.tif](https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_lf_8.tif) (GeoTIFF)

<img src="README-img/sonoma-county-ladder-fuels-4m.png" width="400">

## hillshade-2022-greyscale

On the map as "2022 hillshade", minimally transformed from the source on [SonomaVegMap](https://sonomavegmap.org/), where it is one of the provided 2022 LIDAR products. We converted from GeoTIFF to PMTiles and projected to EPSG:3857.

* [https://gully-map.cdn.uchicago-dsi.org/hillshade-2022-greyscale.pmtiles](https://gully-map.cdn.uchicago-dsi.org/hillshade-2022-greyscale.pmtiles) (2.9 GiB)
* `http://localhost:8080/data/hillshade-2022-greyscale/{z}/{x}/{y}.webp`
* format: WEBP
* tile size: 512
* zoom: 9..18
* bounds: -123.5416832, 38.0989466, -122.3315485, 38.8578298
* original source: https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_behs.tif (GeoTIFF)

<img src="README-img/hillshade-2022-greyscale.png" width="400">

## hillshade-2022-color-enhanced

On the map as "2022 color-enhanced hillshade," this view of the data was suggested by Adam Cummings. It is an [overlay](https://en.wikipedia.org/wiki/Blend_modes#Overlay) of greyscale hillshade (above) and the elevation with fractional Laplace sharpening algorithm [described here](https://landscapearchaeology.org/2021/texture-shading/), colored blue to yellow. The implementation we used is [src/oaec_found_gully/texture_algorithm.py](https://github.com/uchicago-dsi/oaec-found-gully/blob/main/src/oaec_found_gully/texture_algorithm.py), derived directly from [zoran-cuckovic/QGIS-terrain-shading](https://github.com/zoran-cuckovic/QGIS-terrain-shading) (and tested to ensure identical output). After applying the algorithm to a single image of the entire county (to minimize the effect of the large edge effects that the sharpening algorithm introduces), we projected to EPSG:3857 and converted to PMTiles.

* [https://gully-map.cdn.uchicago-dsi.org/hillshade-2022-color-enhanced.pmtiles](https://gully-map.cdn.uchicago-dsi.org/hillshade-2022-color-enhanced.pmtiles) (149.0 GiB)
* `http://localhost:8080/data/hillshade-2022-color-enhanced/{z}/{x}/{y}.png`
* format: PNG
* tile size: 512
* zoom: 9..18
* bounds: -123.5416832, 38.0989466, -122.3315485, 38.8578298
* alternate format: [hillshade-2022-color-enhanced.tif](https://gully-map.cdn.uchicago-dsi.org/hillshade-2022-color-enhanced.tif) (51.5 GiB)
* original source: grey hillshade (above) and 2022 elevation DTM ([https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_DTM_2022.zip](https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_DTM_2022.zip)).

<img src="README-img/hillshade-2022-color-enhanced.png" width="400">

## elevation-2022-contours

On the map as "... with 10 m contours," these contour lines were drawn from the 2022 elevation DTM using the `gdal_contour` commandline tool. The projection to EPSG:3857 was performed on the vector contour lines; the original raster was not warped to produce this data product.

* [https://gully-map.cdn.uchicago-dsi.org/elevation-2022-contours.pmtiles](https://gully-map.cdn.uchicago-dsi.org/elevation-2022-contours.pmtiles) (17.7 GiB)
* `http://localhost:8080/data/elevation-2022-contours/{z}/{x}/{y}.pbf`
* format: PBF
* zoom: 9..24
* bounds: -123.534363, 38.115357, -122.35339, 38.853807
* layer: `contours`
* fields: `level`
* alternate format: [elevation-2022-contours.geojson.zip](https://gully-map.cdn.uchicago-dsi.org/elevation-2022-contours.geojson.zip) (5.0 GiB)
* original source: [https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_DTM_2022.zip](https://s3.us-west-1.wasabisys.com/lidarderivs/Sonoma_DTM_2022.zip)

<img src="README-img/elevation-2022-contours.png" width="400">

## elevation-2022-minus-2013

This data product is not on the map, but it is an intermediate step to produce elevation-2022-minus-2013-contours, below. The 2013 elevation DTM is also provided by [SonomaVegMap](https://sonomavegmap.org/), but as a directory of files, one per watershed. The [data/download-LIDAR-2013/procedure.txt](https://github.com/uchicago-dsi/oaec-found-gully/blob/main/data/download-LIDAR-2013/procedure.txt) was used to find and extract them all. The 2013 projection differs from the 2022 data and it uses units of feet, rather than meters (both horizontally and vertically). To produce an elevation difference, all of the 2013 watershed files were projected into the 2022 coordinate system and merged into a single file with `gdal_merge`. (The vertical units had to be manually transformed.) Conversion to EPSG:3857 was performed _after_ computing the difference in the 2022 coordinate system. Both the single-channel GeoTIFF and the PMTiles are in EPSG:3857. PMTiles are colored purple for erosion (2022 has a lower elevation than 2013) and green for deposition. (I later changed the color scheme to orange for deposition so that it would show up against aerial photography, but it's hard to recolor a large PMTiles dataset.)

* [https://gully-map.cdn.uchicago-dsi.org/elevation-2022-minus-2013.pmtiles](https://gully-map.cdn.uchicago-dsi.org/elevation-2022-minus-2013.pmtiles) (5.7 GiB)
* `http://localhost:8080/data/elevation-2022-minus-2013/{z}/{x}/{y}.png`
* format: PNG
* tile size: 512
* zoom: 12..16
* bounds: -123.5416832, 38.0989466, -122.3315485, 38.8578298
* alternate format: [https://gully-map.cdn.uchicago-dsi.org/elevation-2022-minus-2013.tif](elevation-2022-minus-2013.tif) (10.3 GiB)
* original source for 2013 data: [https://www.arcgis.com/home/webmap/viewer.html?webmap=26c0c08f9fcc47c4b905b7e109e38b70&extent=-123.3547,38.4237,-122.6316,38.7816](https://www.arcgis.com/home/webmap/viewer.html?webmap=26c0c08f9fcc47c4b905b7e109e38b70&extent=-123.3547,38.4237,-122.6316,38.7816)

<img src="README-img/elevation-2022-minus-2013.png" width="400">

## elevation-2022-minus-2013-contours

On the map as "2013-2022 elevation difference contours," these are contour lines of the 2022 minus 2013 elevation difference with 1/3 meter spacing (i.e. approximately one foot). The contour lines only range from -3 meters to +3 meters; more extreme changes in elevation are not represented. The contours are computed by [scripts/elevation-difference-contours.py](https://github.com/uchicago-dsi/oaec-found-gully/blob/main/scripts/elevation-difference-contours.py) using Scikit-Image and projected as EPSG:4326 _after_ contouring. Any closed loops are represented as Polygons; any open lines are LineStrings.

* [https://gully-map.cdn.uchicago-dsi.org/elevation-2022-minus-2013-contours.pmtiles](https://gully-map.cdn.uchicago-dsi.org/elevation-2022-minus-2013-contours.pmtiles) (11.8 GiB)
* `http://localhost:8080/data/elevation-2022-minus-2013-contours/{z}/{x}/{y}.pbf`
* format: PBF
* zoom: 9..24
* bounds: -123.534602, 38.109024, -122.348627, 38.853763
* layer: `contours`
* fields: `level`
* alternate format: [elevation-2022-minus-2013-contours.geojson.zip](https://gully-map.cdn.uchicago-dsi.org/elevation-2022-minus-2013-contours.geojson.zip) (3.0 GiB)

<img src="README-img/elevation-2022-minus-2013-contours.png" width="400">

## gully-detection-pass2

On the map as "Gully detection probability," this is the output of the linear combination model implemented in [scripts/find_gully.py](https://github.com/uchicago-dsi/oaec-found-gully/blob/main/scripts/find_gullies.py), colored light blue (same color as water on the basic map) and projected as EPSG:3857. It doesn't show up well and is mostly useful as a stepping stone to gully-detection-pass3-graph (below).

* [https://gully-map.cdn.uchicago-dsi.org/gully-detection-pass2.pmtiles](https://gully-map.cdn.uchicago-dsi.org/gully-detection-pass2.pmtiles) (842.8 MiB)
* `http://localhost:8080/data/gully-detection-pass2/{z}/{x}/{y}.png`
* format: PNG
* tile size: 512
* zoom: 0..16
* bounds: -123.5428349, 38.1033256, -122.3328823, 39.242092

<img src="README-img/gully-detection-pass2.png" width="400">

## gully-detection-pass3-graph

On the map as "Gully paths as lines," this is the output of the skeletonization algorithm implemented in [scripts/pass3-graphs-to-parquet.py]([https://github.com/uchicago-dsi/oaec-found-gully/blob/main/scripts/find_gullies.py](https://github.com/uchicago-dsi/oaec-found-gully/blob/main/scripts/pass3-graphs-to-parquet.py)). It is a vector quantity, served as vector tiles (in EPSG:4326) and a Parquet file (not currently used by the map).

* [https://gully-map.cdn.uchicago-dsi.org/gully-detection-pass3-graph.pmtiles](https://gully-map.cdn.uchicago-dsi.org/gully-detection-pass3-graph.pmtiles) (33.6 MiB)
* `http://localhost:8080/data/gully-detection-pass3-graph/{z}/{x}/{y}.pbf`
* format: PBF
* zoom: 9..16
* bounds: -123.533896, 38.117104, -122.357284, 38.85363
* layer: `gully_detection_pass3_graph`
* fields: _(none!)_
* alternate format: [gully-detection-pass3-graph.parquet](https://gully-map.cdn.uchicago-dsi.org/gully-detection-pass3-graph.parquet) (47.9 MiB)

<img src="README-img/gully-detection-pass3-graph.png" width="400">

To use the Parquet file, install `geopy`, `awkward` ([Awkward Array](https://awkward-array.org/)), `pyarrow`, `fsspec`, and `aiohttp` and run

```python
>>> import awkward as ak
>>> gullies = ak.from_parquet("https://gully-map.cdn.uchicago-dsi.org/gully-detection-pass3-graph.parquet")
>>> gullies.type.show()
139 * {
    watersheds: ?string,
    endpoints_lon: option[var * ?float64],
    endpoints_lat: option[var * ?float64],
    endpoints_junction_count: option[var * ?int64],
    paths_lon: option[var * option[var * ?float64]],
    paths_lat: option[var * option[var * ?float64]],
    paths_start_endpoint_id: option[var * ?int64],
    paths_stop_endpoint_id: option[var * ?int64]
}
```

The `endpoints_lon`/`endpoints_lat` are nodes of the graph and `paths_lon`/`paths_lat` are edges, with `paths_start_endpoint_id` and `paths_stop_endpoint_id` to indicate which paths connect to which nodes by index. The outermost lists are watersheds and nested lists within are all gullies for each watershed. If you're going to iterate over the data with Python for loops, I recommend first converting from Awkward Arrays to native Python lists with `.tolist()` for performance (and if you need higher performance, use Numba on the original Awkward Arrays).

## elevation-2013 and elevation-2022

On the map as the "Elevation along line" feature, these tiles are not visualized on the map, but they're used to perform calculations. The 2013 and 2022 DTM elevations, described above, are projected to EPSG:3857 with a common array grid. The GeoTIFFs are single-channel float32, and the PMTiles present the same data in tiles, but with a `reinterpret_cast` as RGBA colors (in little-endian order). This image representation is not in itself meaningful, but PMTiles must be RGBA.

* [https://gully-map.cdn.uchicago-dsi.org/elevation-2013.pmtiles](https://gully-map.cdn.uchicago-dsi.org/elevation-2013.pmtiles) (11.7 GiB)
* [https://gully-map.cdn.uchicago-dsi.org/elevation-2022.pmtiles](https://gully-map.cdn.uchicago-dsi.org/elevation-2022.pmtiles) (10.4 GiB)
* `http://localhost:8080/data/elevation-2013/{z}/{x}/{y}.png`
* `http://localhost:8080/data/elevation-2022/{z}/{x}/{y}.png`
* format: PNG
* tile size: 256
* zoom: 17..17
* bounds (2013): -123.5479195, 38.0969493, -122.343146, 39.2461077
* bounds (2022): -123.5416832, 38.0989466, -122.3315485, 38.8578298
* alternate format: [elevation-2013.tif](https://gully-map.cdn.uchicago-dsi.org/elevation-2013.tif) (64.8 GiB)
* alternate format: [elevation-2022.tif](https://gully-map.cdn.uchicago-dsi.org/elevation-2022.tif) (62.8 GiB)

<img src="README-img/elevation-2022.png" width="400">
