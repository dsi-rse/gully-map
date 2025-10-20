<script lang="ts">
  import { onMount } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import { MapLibre } from 'svelte-maplibre';
  import { Protocol } from 'pmtiles';
  import mapStyle from './map-style.json';

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

  let map;
  function handleOnLoad(theMap) {
    map = theMap;
  }

  function toggleBaselayer(layer) {
    if (layer == "basic") {
      map.setPaintProperty("aerial_2013", "raster-opacity", 0);
      map.setPaintProperty("aerial_2021", "raster-opacity", 0);
      map.setPaintProperty("parcels", "line-opacity", 0.5);
    }
    else if (layer == "aerial_2013") {
      map.setPaintProperty("aerial_2013", "raster-opacity", 1);
      map.setPaintProperty("aerial_2021", "raster-opacity", 0);
      map.setPaintProperty("parcels", "line-opacity", 0.5);
    }
    else if (layer == "aerial_2022") {
      map.setPaintProperty("aerial_2013", "raster-opacity", 0);
      map.setPaintProperty("aerial_2021", "raster-opacity", 1);
      map.setPaintProperty("parcels", "line-opacity", 1);
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
      }}
      />
  </div>
  <div class="divider" on:mousedown={startDrag}></div>
  <div class="right-half" style="width: calc(100vw - 10px - {leftWidth}px);">
    <div>
      <h3>Map layers</h3>
      <div id="zoom_in_message" class="group">(Zoom in to enable high-resolution layers.)</div>
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
