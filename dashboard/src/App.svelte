<script lang="ts">
  import { MapLibre } from 'svelte-maplibre';
</script>

<div class="whole-page">
  <div class="left-half">
    <MapLibre 
      center={[50,20]}
      zoom={7}
      class="map"
      standardControls
      style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
      />
  </div>
  <div class="right-half">
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
    width: 50vw;
    height: 100vh;
    min-width: 200px;
    position: relative;
  }

  :global(.right-half) {
    width: 50vw;
    height: 100vh;
    overflow-y: auto;
    padding: 1rem;
    box-sizing: border-box;
  }

  :global(.map) {
    width: 100%;
    height: 100vh;
  }
</style>
