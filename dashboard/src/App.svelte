<script lang="ts">
  import { onMount } from "svelte";
  import maplibregl from "maplibre-gl";
  import { MapLibre } from "svelte-maplibre";
  import { PMTiles, Protocol } from "pmtiles";
  import upng from "upng-js";

  import mapStyle from "./map-style.json";

  window.PMTiles = PMTiles;
  window.upng = upng;

  let protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  let leftWidth = 0.65 * window.innerWidth;
  let dragging = false;

  function startDrag(e: MouseEvent) {
    dragging = true;
    document.body.style.cursor = "col-resize";
  }

  function stopDrag() {
    dragging = false;
    document.body.style.cursor = "";
  }

  function onDrag(e: MouseEvent) {
    if (dragging) {
      let min = 200, max = window.innerWidth - 200;
      let x = Math.min(max, Math.max(min, e.clientX));
      leftWidth = x;
    }
  }

  onMount(() => {
    window.addEventListener("mousemove", onDrag);
    window.addEventListener("mouseup", stopDrag);
    return () => {
      window.removeEventListener("mousemove", onDrag);
      window.removeEventListener("mouseup", stopDrag);
    };
  });

  let map = null;
  function handleOnLoad(theMap) {
    map = theMap;
  }

  function toggleBaselayer(layer) {
    if (map != null) {
      if (layer == "basic") {
        map.setLayoutProperty("aerial_2013", "visibility", "none");
        map.setLayoutProperty("aerial_2021", "visibility", "none");
        map.setPaintProperty("parcels", "line-opacity", 0.5);
      }
      else if (layer == "aerial_2013") {
        map.setLayoutProperty("aerial_2013", "visibility", "visible");
        map.setLayoutProperty("aerial_2021", "visibility", "none");
        map.setPaintProperty("parcels", "line-opacity", 0.5);
      }
      else if (layer == "aerial_2022") {
        map.setLayoutProperty("aerial_2013", "visibility", "none");
        map.setLayoutProperty("aerial_2021", "visibility", "visible");
        map.setPaintProperty("parcels", "line-opacity", 1);
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

  const TILE_SIZE = 256;
  const elevation2013 = new PMTiles("https://uchicago-dsi-oaec.s3.us-east-1.amazonaws.com/elevation-2013.pmtiles");
  const elevation2022 = new PMTiles("https://uchicago-dsi-oaec.s3.us-east-1.amazonaws.com/elevation-2022.pmtiles");

  async function tile_and_pixel_position(event, tile_z) {
    const lng = event.lngLat.lng;
    const lat = event.lngLat.lat;

    const tile_x = Math.floor((lng + 180) / 360 * Math.pow(2, tile_z));
    const tile_y = Math.floor((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, tile_z));

    const scale = TILE_SIZE * Math.pow(2, tile_z);
    const world_x = (lng + 180) / 360;
    const sinLat = Math.sin(lat * Math.PI / 180);
    const world_y = 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI);
    const pixel_x = Math.round(world_x * scale);
    const pixel_y = Math.round(world_y * scale);

    const tile_pixel_x = pixel_x % TILE_SIZE;
    const tile_pixel_y = pixel_y % TILE_SIZE;

    return [tile_x, tile_y, tile_pixel_x, tile_pixel_y];
  }

  async function get_elevation(event, tile_z) {
    const [tile_x, tile_y, tile_pixel_x, tile_pixel_y] = await tile_and_pixel_position(event, tile_z);
    const index = tile_pixel_y * TILE_SIZE + tile_pixel_x;

    const response2013_promise = elevation2013.getZxy(tile_z, tile_x, tile_y);
    const response2022_promise = elevation2022.getZxy(tile_z, tile_x, tile_y);
    const response2013 = await response2013_promise;
    const response2022 = await response2022_promise;
    if (response2013) {
      const img = upng.decode(response2013.data);
      const rgba = upng.toRGBA8(img)[0];  // first and only frame
      const view = new DataView(rgba, 0, rgba.length);
      const value = view.getFloat32(4 * index, true);
      if (value < 3e38) {
        document.getElementById("elevation_2013").innerHTML = `${value} meters`;
      }
      else {
        document.getElementById("elevation_2013").innerHTML = "out of bounds";
      }
    }
    if (response2022) {
      const img = upng.decode(response2022.data);
      const rgba = upng.toRGBA8(img)[0];  // first and only frame
      const view = new DataView(rgba, 0, rgba.length);
      const value = view.getFloat32(4 * index, true);
      if (value < 3e38) {
        document.getElementById("elevation_2022").innerHTML = `${value} meters`;
      }
      else {
        document.getElementById("elevation_2022").innerHTML = "out of bounds";
      }
    }
  }

  const highres_layers = [
    "baselayer_aerial_2013",
    "baselayer_aerial_2021",
    "layer_parcel",
  ];

</script>

<div class="whole-page"> 
  <div class="left-half" style="width: {leftWidth}px;">
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
        get_elevation(e, 17);
      }}
      />
  </div>
  <div class="divider" on:mousedown={startDrag}></div>
  <div class="right-half" style="width: calc(100vw - 10px - {leftWidth}px);">
    <div>
      <div id="zoom_in_message" class="group">(Zoom in to turn on the disabled layers.)</div>
      <div class="group">
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
      </div>
      <div class="group">
        <div>
          <label for="layer_parcel" class="disabled"><input type="checkbox" id="layer_parcel" disabled on:change={
                (e) => map.setLayoutProperty("parcels", "visibility", e.target.checked ? "visible" : "none")
            }> Land ownership boundaries</label> (<a href="https://gis.sonomacounty.ca.gov/maps/4b231e8ffbac47abb9a78296e550ffa1">source</a>)
        </div>
      </div>
      <div class="group">
        <div style="margin-left: 11px;">Last clicked in:</div>
        <div id="last_clicked_in" style="min-height: 1em; margin: 5px; padding: 5px; border: 1px solid gray;"></div>
      </div>
      <div class="group">
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
        <div>
           (See page 9 of <a href="https://tukmangeospatial.egnyte.com/dl/ADWSBBL7ac">LIDAR derivatives</a>)
        </div>
      </div>
      <div class="group">
        <div>
          <label><input type="checkbox" name="gully_detection_pass2" on:change={
              (e) => {
                  if (map) {
                      map.setLayoutProperty("gully_detection_pass2", "visibility", e.target.checked ? "visible" : "none");
                  }
              }
          }> Gully detection probability</label>
        </div>
      </div>
      <div class="group">
        <div>Elevation in 2013: <span id="elevation_2013">click somewhere</span></div>
        <div>Elevation in 2022: <span id="elevation_2022">click somewhere</span></div>
      </div>
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

  :global(.map) {
    width: 100%;
    height: 100vh;
  }
</style>
