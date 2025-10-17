<script lang="ts">
  import { onMount } from 'svelte';
  import { MapLibre } from 'svelte-maplibre';
  import mapStyle from './map-style.json';

  let leftWidth = 0.7 * window.innerWidth;
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
    }
    else if (layer == "aerial_2013") {
      map.setPaintProperty("aerial_2013", "raster-opacity", 1);
      map.setPaintProperty("aerial_2021", "raster-opacity", 0);
    }
    else if (layer == "aerial_2022") {
      map.setPaintProperty("aerial_2013", "raster-opacity", 0);
      map.setPaintProperty("aerial_2021", "raster-opacity", 1);
    }
  }

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
      onzoomend={({ target: map }) => {
          if (map.getZoom() < 14) {
              toggleBaselayer("basic");
              document.getElementById("baselayer_basic").checked = true;
              document.getElementById("baselayer_aerial_2013").disabled = true;
              document.getElementById("baselayer_aerial_2021").disabled = true;
              document.querySelector('label[for="baselayer_aerial_2013"]').classList.add("disabled");
              document.querySelector('label[for="baselayer_aerial_2021"]').classList.add("disabled");
              document.getElementById("zoom_in_message").style.display = "block";
          }
          else {
              document.getElementById("baselayer_aerial_2013").disabled = false;
              document.getElementById("baselayer_aerial_2021").disabled = false;
              document.querySelector('label[for="baselayer_aerial_2013"]').classList.remove("disabled");
              document.querySelector('label[for="baselayer_aerial_2021"]').classList.remove("disabled");
              document.getElementById("zoom_in_message").style.display = "none";
          }
      }}
      />
  </div>
  <div class="divider" on:mousedown={startDrag}></div>
  <div class="right-half" style="width: calc(100vw - 10px - {leftWidth}px);">
    <div>
      <h3>Map layers</h3>
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
      <div id="zoom_in_message" style="margin-left: 25px;">(Zoom in to enable aerial photography.)</div>
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
    cursor: not-allowed;
  }

  :global(.map) {
    width: 100%;
    height: 100vh;
  }
</style>
