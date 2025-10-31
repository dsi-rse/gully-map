<script lang="ts">
  import { onMount } from "svelte";
  import maplibregl from "maplibre-gl";
  import { MapLibre } from "svelte-maplibre";
  import { parquetRead } from "hyparquet";
  import { PMTiles, Protocol } from "pmtiles";
  import upng from "upng-js";
  import { getDistance } from "geolib";
  import uPlot from "uplot";
  import "uplot/dist/uPlot.min.css";

  import mapStyle from "./map-style.json";

  window.PMTiles = PMTiles;
  window.upng = upng;

  let protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  let rightWidth = 0.35 * window.innerWidth;
  let horizontalPaneDragging = false;

  let elevation_plot;
  let elevation_difference_plot;

  function elevationPlotWidth() {
    return document.getElementById("elevation_plot")?.clientWidth  ||  300;
  }

  function elevationPlotHeight() {
    return elevationPlotWidth() * 2/3;
  }

  function startHorizontalPaneDrag(e: MouseEvent) {
    horizontalPaneDragging = true;
    document.body.style.cursor = "col-resize";
  }

  function stopHorizontalPaneDrag() {
    horizontalPaneDragging = false;
    document.body.style.cursor = "";
  }

  function onHorizontalPaneDrag(e: MouseEvent) {
    if (horizontalPaneDragging) {
      let min = 200, max = window.innerWidth - 200;
      let x = Math.min(max, Math.max(min, e.clientX));
      rightWidth = window.innerWidth - x;

      if (elevation_plot) {
        elevation_plot.setSize({ width: elevationPlotWidth(), height: elevationPlotHeight() });
      }
      if (elevation_difference_plot) {
        elevation_difference_plot.setSize({ width: elevationPlotWidth(), height: elevationPlotHeight() });
      }
    }
  }

  function hideBaselayer(e) {
    map.setPaintProperty("contrast", "background-opacity", 1 - e.target.value);
  }

  onMount(() => {
    window.addEventListener("mousemove", onHorizontalPaneDrag);
    window.addEventListener("mouseup", stopHorizontalPaneDrag);

    document.getElementById("baselayer_slider").addEventListener("input", hideBaselayer);

    elevation_plot = new uPlot(
      {
        width: elevationPlotWidth(),
        height: elevationPlotHeight(),
        series: [
          { label: "distance" },
          { label: "2013 elevation", stroke: "#ff7f0e" },
          { label: "2022 elevation", stroke: "#1f77b4" },
        ],
        axes: [
          { label: "distance along curve (meters)", labelFont: "12px Arial", size: 40 },
          { label: "elevation (meters)", labelFont: "12px Arial", size: 50 },
        ],
        scales: { "x": { time: false } },
        padding: [8, 8, 0, 0],
      },
      [
        [], [], [],
      ],
      document.getElementById("elevation_plot"),
    );
    elevation_difference_plot = new uPlot(
      {
        width: elevationPlotWidth(),
        height: elevationPlotHeight(),
        series: [
          { label: "distance" },
          { label: "elevation difference", stroke: "#2ca02c" },
        ],
        axes: [
          { label: "distance along curve (meters)", labelFont: "12px Arial", size: 40 },
          { label: "2022 minus 2013 (meters)", labelFont: "12px Arial", size: 50 },
        ],
        scales: { "x": { time: false } },
        padding: [8, 8, 0, 0],
      },
      [
        [], [], [],
      ],
      document.getElementById("elevation_difference_plot"),
    );

    return () => {
      window.removeEventListener("mousemove", onHorizontalPaneDrag);
      window.removeEventListener("mouseup", stopHorizontalPaneDrag);
    };
  });

  let map = null;
  function handleOnLoad(theMap) {
    map = theMap;

    map.boxZoom.disable();
    map.on("mousedown", handleMapMouseDown);
    map.on("mousemove", handleMapMouseMove);
  }

  function toggleBaselayer(layer) {
    if (map != null) {
      if (layer == "basic") {
        map.setLayoutProperty("aerial_2013", "visibility", "none");
        map.setLayoutProperty("aerial_2021", "visibility", "none");
        map.setLayoutProperty("elevation_difference", "visibility", "none");
      }
      else if (layer == "aerial_2013") {
        map.setLayoutProperty("aerial_2013", "visibility", "visible");
        map.setLayoutProperty("aerial_2021", "visibility", "none");
        map.setLayoutProperty("elevation_difference", "visibility", "none");
      }
      else if (layer == "aerial_2022") {
        map.setLayoutProperty("aerial_2013", "visibility", "none");
        map.setLayoutProperty("aerial_2021", "visibility", "visible");
        map.setLayoutProperty("elevation_difference", "visibility", "none");
      }
      else if (layer == "elevation_difference") {
        map.setLayoutProperty("aerial_2013", "visibility", "none");
        map.setLayoutProperty("aerial_2021", "visibility", "none");
        map.setLayoutProperty("elevation_difference", "visibility", "visible");
      }
    }
  }

  function toggleLadderLayer(layer) {
    if (map != null) {
      if (layer == "none") {
        map.setLayoutProperty("ladder_fuels_4m", "visibility", "none");
        map.setLayoutProperty("ladder_fuels_8m", "visibility", "none");
      }
      else if (layer == "4m") {
        map.setLayoutProperty("ladder_fuels_4m", "visibility", "visible");
        map.setLayoutProperty("ladder_fuels_8m", "visibility", "none");
      }
      else if (layer == "8m") {
        map.setLayoutProperty("ladder_fuels_4m", "visibility", "none");
        map.setLayoutProperty("ladder_fuels_8m", "visibility", "visible");
      }
    }
  }

  function toggleElevationContours() {
    if (map) {
      let yes_contours = document.getElementById("elevation_difference_contours").checked;
      let yes_fill = document.getElementById("elevation_difference_contours_fill").checked;
      map.setLayoutProperty("elevation_difference_contour_minus_fill", "visibility", yes_contours && yes_fill ? "visible" : "none");
      map.setLayoutProperty("elevation_difference_contour_plus_fill", "visibility", yes_contours && yes_fill ? "visible" : "none");
      map.setLayoutProperty("elevation_difference_contour_minus", "visibility", yes_contours ? "visible" : "none");
      map.setLayoutProperty("elevation_difference_contour_plus", "visibility", yes_contours ? "visible" : "none");
    }
  }

  // fetch("https://uchicago-dsi-oaec.s3.us-east-1.amazonaws.com/gully-detection-pass3-graph.parquet").then(async response => {
  //   if (!response.ok) {
  //     return;
  //   }
  //   let parquetFile = await response.arrayBuffer();

  //   new Promise((onComplete) => parquetRead({
  //     file: parquetFile,
  //     columns: ["paths_lon", "paths_lat"],
  //     rowStart: 0,
  //     rowEnd: 139,  // number of watersheds in Sonoma County
  //     onComplete,
  //   })).then(data => {
  //     console.log(data);
  //   });
  // });

  let checkboxUserEnabled = false;
  let shiftDown = false;

  $: drawToggleChecked = checkboxUserEnabled  ||  shiftDown;

  function isDrawEnabled() {
    return checkboxUserEnabled  ||  shiftDown;
  }

  // drawing state
  let drawState = "idle";  // "idle" | "freehand" | "awaiting-second-click"
  let drawPoints = [];

  function handleMapMouseDown(e) {
    if (!isDrawEnabled()  ||  e.originalEvent.button !== 0  ||  map === null) {
      return;
    }

    if (drawState === "awaiting-second-click") {
      // second click: finish straight line
      finishStraightLine(e);
      return;
    }

    // not currently drawing: a new drawing session
    let moved = false;
    let first = true;

    function moveListener(e2) {
      if (!first  &&  drawState === "idle") {
        map.off("mousemove", moveListener);
        map.off("mouseup", upListener);
        map.dragPan.enable();
        return;
      }
      first = false;

      moved = true;
      if (drawState !== "freehand") {
        startFreehand(e);
      }
      updateFreehand(e2);
    }

    function upListener(e2) {
      first = false;

      map.off("mousemove", moveListener);
      map.off("mouseup", upListener);
      map.dragPan.enable();

      if (drawState === "freehand") {
        finishFreehand();
      }
      else if (!moved) {
        // this was a click, not drag: enter straight line mode and wait
        startStraightLine(e2);
      }
      else {
        cancelDrawing(); // defensive (shouldn't reach here)
      }
    }

    map.dragPan.disable();
    map.on("mousemove", moveListener);
    map.on("mouseup", upListener);
  }

  function startFreehand(e) {
    drawState = "freehand";
    drawPoints = [[e.lngLat.lng, e.lngLat.lat]];
    updateDrawLine();
  }

  function updateFreehand(e) {
    if (drawState !== "freehand") {
      return;
    }

    const here = [e.lngLat.lng, e.lngLat.lat];
    const last = drawPoints[drawPoints.length - 1];
    if (last[0] !== here[0] || last[1] !== here[1]) {
      drawPoints.push(here);
      updateDrawLine();
      updatePlot(drawPoints, false);
    }
  }

  function finishFreehand() {
    if (drawState === "freehand" && drawPoints.length > 1) {
      updatePlot(drawPoints, true);
    }
    cancelDrawing();
  }

  function startStraightLine(e) {
    drawState = "awaiting-second-click";
    const pt = [e.lngLat.lng, e.lngLat.lat];
    drawPoints = [pt, pt];
    updateDrawLine();
  }

  function interpolatePoints(coords) {
    // interpolate 100 intermediate points
    return Array.from({ length: 100 }, (_, i) => {
      const t = i / 99;
      return [
        coords[0][0] * (1 - t) + coords[coords.length - 1][0] * t,
        coords[0][1] * (1 - t) + coords[coords.length - 1][1] * t,
      ];
    });
  }

  function updateStraightLine(e) {
    if (drawState !== "awaiting-second-click") {
      return;
    }
    drawPoints[1] = [e.lngLat.lng, e.lngLat.lat];
    updateDrawLine();
    updatePlot(interpolatePoints(drawPoints), false);
  }

  function finishStraightLine(e) {
    if (drawState !== "awaiting-second-click") {
      return;
    }
    drawPoints[1] = [e.lngLat.lng, e.lngLat.lat];
    updatePlot(interpolatePoints(drawPoints), true);
    cancelDrawing();
  }

  function cancelDrawing() {
    drawState = "idle";
  }

  function handleMapMouseMove(e) {
    let did_something = false;
    if (drawState === "awaiting-second-click") {
      did_something = true;
      updateStraightLine(e);
    }
  }

  function handleDrawToggleChange(e) {
    checkboxUserEnabled = e.target.checked;
    if (!isDrawEnabled()  &&  drawState !== "idle") {
      cancelDrawing();
    }
  }

  function handleWindowKeydown(e) {
    if (e.key === "Shift"  &&  !shiftDown) {
      shiftDown = true;
    }
  }

  function handleWindowKeyup(e) {
    if (e.key === "Shift"  &&  shiftDown) {
      shiftDown = false;
      cancelDrawing();
    }
  }

  function onDrawToggleChange(e) {
    checkboxUserEnabled = e.target.checked;
    if (!isDrawEnabled()  &&  drawState !== "idle") {
      cancelDrawing();
    }
  }

  function updateDrawLine() {
    if (map) {
      let source = map.getSource("draw-line");
      if (source) {
        source.setData({
          type: "Feature",
          geometry: {
            type: "LineString",
            coordinates: drawPoints  &&  drawPoints.length >= 2 ? drawPoints : [],
          },
        });
      }
    }
  }

  const TILE_SIZE = 256;
  const TILE_Z = 17
  const elevation2013 = new PMTiles("https://uchicago-dsi-oaec.s3.us-east-1.amazonaws.com/elevation-2013.pmtiles");
  const elevation2022 = new PMTiles("https://uchicago-dsi-oaec.s3.us-east-1.amazonaws.com/elevation-2022.pmtiles");

  const TILE_CACHE_SIZE = 100;  // number of tiles to keep in memory
  let tileCache = {};
  let tileCacheOrder = [];  // first is oldest, last is newest

  function getTile(tile_x, tile_y) {
    const key = `${tile_x}:${tile_y}`;

    if (tileCache.hasOwnProperty(key)) {
      // "touch" this tile, moving it to the top of the cache, and return it
      const index = tileCacheOrder.indexOf(key);
      if (index < tileCacheOrder.length - 1) {
        tileCacheOrder.splice(index, 1);
        tileCacheOrder.push(key);
      }
      return tileCache[key];
    }
    else {
      // actually download the tile
      const tile = downloadTile(tile_x, tile_y);

      // add the tile to the top of the cache, possibly evicting the bottom
      tileCache[key] = tile;
      tileCacheOrder.push(key);
      if (tileCacheOrder.length > TILE_CACHE_SIZE) {
        delete tileCache[tileCacheOrder[0]];
        tileCacheOrder.shift();
      }

      return tile;
    }
  }

  function downloadTile(tile_x, tile_y) {
    function toView(response) {
      if (response) {
        const img = upng.decode(response.data);
        const rgba = upng.toRGBA8(img)[0];  // first and only frame
        return new DataView(rgba, 0, rgba.length);
      }
      else {
        return null;
      }
    }

    function getValue(view, x, y) {
      if (view  &&  0 <= x  &&  x < TILE_SIZE  &&  0 <= y  &&  y < TILE_SIZE) {
        const index = y * TILE_SIZE + x;
        const value = view.getFloat32(4 * index, true);
        return value < 3e38 ? value : null;
      }
      else {
        return null;
      }
    }

    let promise2013 = elevation2013.getZxy(TILE_Z, tile_x, tile_y);
    let view2013 = null;
    let errors2013 = [];
    let retries2013 = 3;
    let waiting2013 = true;

    function handleError2013(error) {
      errors2013.push(error);
      if (retries2013 > 0) {
        retries2013--;
        promise2013 = elevation2013.getZxy(TILE_Z, tile_x, tile_y);
        promise2013.then(
          response => { view2013 = toView(response);  waiting2013 = false; },
          handleError2013,
        );
      }
      else {
        waiting2013 = false;
      }
    }
    promise2013.then(
      response => { view2013 = toView(response);  waiting2013 = false; },
      handleError2013,
    );

    let promise2022 = elevation2022.getZxy(TILE_Z, tile_x, tile_y);
    let view2022 = null;
    let errors2022 = [];
    let retries2022 = 3;
    let waiting2022 = true;

    function handleError2022(error) {
      errors2022.push(error);
      if (retries2022 > 0) {
        retries2022--;
        promise2022 = elevation2022.getZxy(TILE_Z, tile_x, tile_y);
        promise2022.then(
          response => { view2022 = toView(response);  waiting2022 = false; },
          handleError2022,
        );
      }
      else {
        waiting2022 = false;
      }
    }
    promise2022.then(
      response => { view2022 = toView(response);  waiting2022 = false; },
      handleError2022,
    );

    return {
      tile_x: tile_x,
      tile_y: tile_y,
      view2013: () => view2013,
      view2022: () => view2022,
      value2013: (x, y) => getValue(view2013, x, y),
      value2022: (x, y) => getValue(view2022, x, y),
      errors2013: () => errors2013,
      errors2022: () => errors2022,
      retries2013: () => retries2013,
      retries2022: () => retries2022,
      waiting2013: () => waiting2013,
      waiting2022: () => waiting2022,
      waiting: () => waiting2013  ||  waiting2022,
    };
  }

  function tileIndex(lng, lat) {
    const tile_x = Math.floor((lng + 180) / 360 * Math.pow(2, TILE_Z));
    const tile_y = Math.floor((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, TILE_Z));
    return [tile_x, tile_y];
  }

  function pixelIndex(lng, lat) {
    const scale = TILE_SIZE * Math.pow(2, TILE_Z);
    const world_x = (lng + 180) / 360;
    const sinLat = Math.sin(lat * Math.PI / 180);
    const world_y = 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI);
    const pixel_x = Math.round(world_x * scale);
    const pixel_y = Math.round(world_y * scale);
    const x = pixel_x % TILE_SIZE;
    const y = pixel_y % TILE_SIZE;
    return [x, y];
  }

  const MAX_TILES_PER_QUERY = 10;
  const CHECK_TIMEOUT = 100;  // ms

  function updatePlot(coords, last) {
    const num_tiles = (new Set(coords.map(([lng, lat]) => tileIndex(lng, lat).join(":")))).size;

    if (num_tiles > MAX_TILES_PER_QUERY) {
      document.getElementById("line-is-too-long").style.display = "block";
      return;
    }
    document.getElementById("line-is-too-long").style.display = "none";

    const firstPoint = { longitude: coords[0][0], latitude: coords[0][1] };
    const distances = coords.map(([lng, lat]) => getDistance(firstPoint, { longitude: lng, latitude: lat }, 0.01));

    const tiles = coords.map(([lng, lat]) => getTile(...tileIndex(lng, lat)));
    const pixelIndexes = coords.map(([lng, lat]) => pixelIndex(lng, lat));

    if (last) {
      async function checkUntilDone() {
        while (true) {
          const isWaiting = tiles.some(tile => tile.waiting());
          const values2013 = tiles.map((tile, i) => tile.value2013(...pixelIndexes[i]));
          const values2022 = tiles.map((tile, i) => tile.value2022(...pixelIndexes[i]));
          drawPlot(distances, values2013, values2022);

          if (!isWaiting) {
            break;
          }
          await new Promise(resolve => setTimeout(resolve, CHECK_TIMEOUT));
        }
      }
      checkUntilDone();
    }
    else {
      const values2013 = tiles.map((tile, i) => tile.value2013(...pixelIndexes[i]));
      const values2022 = tiles.map((tile, i) => tile.value2022(...pixelIndexes[i]));
      drawPlot(distances, values2013, values2022);
    }
  }

  function drawPlot(distances, values2013, values2022) {
    if (values2013.every(x => x === null)  &&  values2022.every(x => x === null)) {
      document.getElementById("elevation_plot").style.display = "none";
      document.getElementById("elevation_difference_plot").style.display = "none";
      return;
    }
    document.getElementById("elevation_plot").style.display = "block";
    document.getElementById("elevation_difference_plot").style.display = "block";

    elevation_plot.setData([distances, values2013, values2022]);
    elevation_difference_plot.setData([distances, values2022.map(
      (x, i) => x === null  &&  values2013[i] === null ? null : x - values2013[i]
    )]);
  }

  const highres_layers = [
    "baselayer_aerial_2013",
    "baselayer_aerial_2021",
    "baselayer_elevation_difference",
  ];

</script>

<svelte:window on:keydown={handleWindowKeydown} on:keyup={handleWindowKeyup} />

<div class="whole-page"> 
  <div class="left-half" style="width: calc(100vw - 10px - {rightWidth}px);">
    <MapLibre
      center={[-122.88, 38.46]}
      zoom={9}
      class="map"
      standardControls
      style={mapStyle}
      onload={handleOnLoad}
      onzoomend={(e) => {
          if (e.target.getZoom() < 14) {
              toggleBaselayer("basic");
              document.getElementById("baselayer_basic").checked = true;
              for (let name of highres_layers) {
                  document.getElementById(name).disabled = true;
                  document.querySelector('label[for="' + name + '"]').classList.add("disabled");
              }
              document.getElementById("zoom_in_message").style.display = "block";
          }
          else {
              for (let name of highres_layers) {
                  document.getElementById(name).disabled = false;
                  document.querySelector('label[for="' + name + '"]').classList.remove("disabled");
              }
              document.getElementById("zoom_in_message").style.display = "none";
          }
      }}
      onclick={(e) => {
        const features = e.target.queryRenderedFeatures(e.point, { layers: ["parcels-filled"] });
        if (features.length == 0) {
            document.getElementById("last_clicked_in").innerHTML = "";
        }
        else {
            const f = features[0].properties;
            document.getElementById("last_clicked_in").innerHTML = `<b>Parcel ID (APN):</b> ${f.parcel}<br>
<b>Address:</b> ${f.address}, ${f.city}<br>
${f.type}; ${f.description}`;
        }
      }}
      />
  </div>
  <div class="divider" on:mousedown={startHorizontalPaneDrag}></div>
  <div class="right-half" style="width: {rightWidth}px;">
    <div>
      <div class="group">
        <h3>Base layer</h3>
        <div>
          <div style="display: flex; width: 100%;">
            <label for="baselayer_slider" style="white-space: nowrap;">Hidden</label>
            <input type="range" style="flex: 1;" id="baselayer_slider" min="0" max="1" step="0.1" value="1">
            <label for="baselayer_slider" style="white-space: nowrap;">Visible</label>
          </div>
        </div>
        <div>
          <label><input type="radio" name="baselayer" id="baselayer_basic" checked on:change={
              (e) => toggleBaselayer("basic")
          }> Basic topographic map</label> (<a href="https://github.com/nst-guide/osm-liberty-topo">from here</a>)
        </div>
        <div>
          <label for="baselayer_aerial_2013" class="disabled"><input type="radio" name="baselayer" id="baselayer_aerial_2013" disabled on:change={
              (e) => toggleBaselayer("aerial_2013")
          }> 2013 aerial photography</label>
          (<a href="https://www.arcgis.com/apps/mapviewer/index.html?url=https://socogis.sonomacounty.ca.gov/image/rest/services/Rasters/Ortho_SoCo_SonomaVeg_2013_WM/ImageServer&source=sd">Sonoma GIS</a>,
          <a href="https://www.arcgis.com/home/item.html?id=a5fc12e9c4324663bafde942a7d1e1d3">through Esri</a>)
        </div>
        <div>
          <label for="baselayer_aerial_2021" class="disabled"><input type="radio" name="baselayer" id="baselayer_aerial_2021" disabled on:change={
              (e) => toggleBaselayer("aerial_2022")
          }> 2021 aerial photography</label>
          (<a href="https://gis.sonomacounty.ca.gov/datasets/dc026cbfb9884d51a65dae1846bf76a5/explore?location=38.472153%2C-122.943650%2C10.18">Sonoma GIS</a>,
          <a href="https://www.arcgis.com/home/item.html?id=0c361a688a5a453487021132c878e870">through Esri</a>)
        </div>
        <div>
          <label for="baselayer_elevation_difference" class="disabled"><input type="radio" name="baselayer" id="baselayer_elevation_difference" disabled on:change={
              (e) => toggleBaselayer("elevation_difference")
          }> 2013-2022 elevation difference</label>
          (<span style="vertical-align: 0.1em; display: inline-block; width: 1em; height: 1em;">
            <svg width="1em" height="1em" viewBox="0 0 24 24" style="display: inline; vertical-align: middle;" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="20" height="20" fill="#b780ff" stroke="#000000" stroke-width="1"/>
            </svg>
          </span> erosion, <span style="vertical-align: 0.1em; display: inline-block; width: 1em; height: 1em;">
            <svg width="1em" height="1em" viewBox="0 0 24 24" style="display: inline; vertical-align: middle;" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="20" height="20" fill="#7ece7e" stroke="#000000" stroke-width="1"/>
            </svg>
          </span> deposition)
        </div>
        <div id="zoom_in_message" class="indent">
          (Zoom in to allow disabled baselayers.)
        </div>
      </div>
      <div class="group">
        <h3>Land ownership</h3>
        <div>
          <label for="layer_parcel"><input type="checkbox" id="layer_parcel" on:change={
                (e) => map.setLayoutProperty("parcels", "visibility", e.target.checked ? "visible" : "none")
            }> Land ownership boundaries</label> (<a href="https://gis.sonomacounty.ca.gov/maps/4b231e8ffbac47abb9a78296e550ffa1">source</a>)
        </div>
      </div>
      <div class="group">
        <div style="margin-left: 11px;">Last clicked in:</div>
        <div id="last_clicked_in" style="min-height: 1em; margin: 5px; padding: 5px; border: 1px solid gray;"></div>
      </div>
      <div class="group">
        <h3>Fire hazard</h3>
        <div>
          <label><input type="radio" name="ladderlayer" id="ladderlayer_none" checked on:change={
              (e) => toggleLadderLayer("none")
          }> Hide ladder fuel proxies</label>
        </div>
        <div>
          <label for="ladderlayer_4m"><input type="radio" name="ladderlayer" id="ladderlayer_4m" on:change={
              (e) => toggleLadderLayer("4m")
          }> (material in 1‒4 m) / (material in 0‒4 m)</label>
        </div>
        <div>
          <label for="ladderlayer_8m"><input type="radio" name="ladderlayer" id="ladderlayer_8m" on:change={
              (e) => toggleLadderLayer("8m")
          }> (material in 1‒8 m) / (material in 0‒8 m)</label>
        </div>
        <div class="indent">
           (See page 9 of <a href="https://tukmangeospatial.egnyte.com/dl/ADWSBBL7ac">LIDAR derivatives</a>)
        </div>
      </div>
      <div class="group">
        <h3>Gullies</h3>
        <div>
          <label><input type="checkbox" name="gully_detection_pass2" on:change={
              (e) => {
                  if (map) {
                      map.setLayoutProperty("gully_detection_pass2", "visibility", e.target.checked ? "visible" : "none");
                  }
              }
          }> Gully detection probability</label>
        </div>
        <div>
          <label><input type="checkbox" name="gully_detection_pass3" on:change={
              (e) => {
                  if (map) {
                      map.setLayoutProperty("gully_detection_pass3_outline", "visibility", e.target.checked ? "visible" : "none");
                      map.setLayoutProperty("gully_detection_pass3", "visibility", e.target.checked ? "visible" : "none");
                  }
              }
          }> Gully paths as lines</label>
        </div>
      </div>
      <div class="group">
        <h3>Erosion</h3>
        <div>
          <label><input type="checkbox" id="elevation_difference_contours" on:change={() => toggleElevationContours()}> 2013-2022 elevation difference contours</label>
        </div>
        <div class="indent">
          (1/3 meter spacing, <span style="vertical-align: 0.1em; display: inline-block; width: 1em; height: 1em;">
            <svg width="1em" height="1em" viewBox="0 0 24 24" style="display: inline; vertical-align: middle;" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="10" stroke="#6f00ff" stroke-width="2" fill="none"/>
              <circle cx="12" cy="12" r="5" stroke="#6f00ff" stroke-width="2" fill="none"/>
            </svg>
          </span> erosion, <span style="vertical-align: 0.1em; display: inline-block; width: 1em; height: 1em;">
            <svg width="1em" height="1em" viewBox="0 0 24 24" style="display: inline; vertical-align: middle;" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="10" stroke="#00a000" stroke-width="2" fill="none"/>
              <circle cx="12" cy="12" r="5" stroke="#00a000" stroke-width="2" fill="none"/>
            </svg>
          </span> deposition)
        </div>
        <div>
          <label><input type="checkbox" id="elevation_difference_contours_fill" checked on:change={() => toggleElevationContours()}> ...and fill in the polygons</label>
        </div>
      </div>
      <div class="group">
        <h3>Elevation along line</h3>
        <div>
          <label for="draw-toggle"><input id="draw-toggle" type="checkbox" bind:checked={drawToggleChecked} on:change={onDrawToggleChange}> Draw line instead of moving map</label>
        </div>
        <div class="indent">
           (holding the <b>shift</b> key temporarily enables this; <b>two clicks</b> for a straight line and <b>drag</b> for a curve)
        </div>
      </div>
      <div class="group">
        <div id="line-is-too-long" style="color: magenta; font-weight: bold; display: none;">Line is too long to measure!</div>
      </div>
      <div id="elevation_plot" style="display: none;"></div>
      <div id="elevation_difference_plot" style="display: none;"></div>
      <div style="height: 300px;"></div>
    </div>
  </div>
</div>

<style>
  :global(body) {
    margin: 0;
  }

  :global(.whole-page) {
    display: flex;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
  }

  :global(.left-half) {
    min-width: 200px;
    max-width: calc(100vw - 200px - 10px);
    height: 100vh;
    position: relative;
    transition: none;
  }

  :global(.divider) {
    width: 10px;
    background: #eee;
    cursor: col-resize;
    height: 100vh;
    z-index: 5;
    position: relative;
    user-select: none;
    transition: background 0.2s;
  }
  :global(.divider):hover,
  :global(.divider):active {
    background: #ccc;
  }

  :global(.right-half) {
    min-width: 200px;
    height: 100vh;
    overflow-y: auto;
    padding: 1rem;
    box-sizing: border-box;
    transition: none;
  }

  :global(label.disabled) {
    color: #aaa;
  }

  :global(.group) {
    margin-bottom: 1em;
  }

  :global(.indent) {
    margin-left: 1.5em;
  }

  :global(.map) {
    width: 100%;
    height: 100vh;
  }
</style>
