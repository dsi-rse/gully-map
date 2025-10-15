<script lang="ts">
  import { onMount } from 'svelte';
  import { MapLibre } from 'svelte-maplibre';

  let leftWidth = window.innerWidth / 2;
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

</script>

<div class="whole-page"> 
  <div class="left-half" style="width: {leftWidth}px;">
   <MapLibre 
      center={[50,20]}
      zoom={7}
      class="map"
      standardControls
      style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
      />
  </div>
  <div class="divider" on:mousedown={startDrag}></div>
  <div class="right-half" style="width: calc(100vw - 10px - {leftWidth}px);">
    <p>Hello!</p>
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

  :global(.map) {
    width: 100%;
    height: 100vh;
  }
</style>
