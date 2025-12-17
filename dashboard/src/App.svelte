<script lang="ts">
  /**
   * Main dashboard component coordinating map interactions, plotting, and UI state.
   */
  import { onMount } from "svelte";
  import maplibregl from "maplibre-gl";
  import type { StyleSpecification } from "maplibre-gl";
  import { MapLibre } from "svelte-maplibre";
  import { Protocol } from "pmtiles";
  import uPlot from "uplot";
  import "uplot/dist/uPlot.min.css";

  import SearchBox from "./lib/SearchBox.svelte";
  import mapStyle from "./map-style.json";

  import { HorizontalPaneController } from "./lib/layout/horizontalPane";
  import { ElevationPlotManager } from "./lib/elevation/elevationPlots";
  import { createLineMeasurementController } from "./lib/elevation/lineMeasurement";
  import { DrawingController } from "./lib/map/drawingController";
  import { PaintController } from "./lib/map/paintController";
  import { updateDrawSources, highlightDrawPoint } from "./lib/map/drawLayers";
  import {
    setBaseLayer,
    setBaseLayerTransparency,
    setContourVisibility,
    setLadderLayer,
    setElevationDifferenceContours,
    getAvailableHighResLayers,
    HIGH_RES_LAYERS,
    type BaseLayerId,
    type LadderLayerId,
  } from "./lib/map/layerControls";

  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  type ParcelInfo = {
    parcel?: string;
    address?: string;
    city?: string;
    type?: string;
    description?: string;
  };

  type MapZoomEvent = { target: maplibregl.Map };

  const INITIAL_ZOOM = 9;

  const mapStyleSpecification = mapStyle as unknown as StyleSpecification;

  let map: maplibregl.Map | null = null;

  let elevationPlotContainer: HTMLDivElement | null = null;
  let elevationPlotElement: HTMLDivElement | null = null;
  let elevationDifferenceElement: HTMLDivElement | null = null;
  let lineTooLongBanner: HTMLDivElement | null = null;
  let elevationSection: HTMLDivElement | null = null;
  let volumeSection: HTMLDivElement | null = null;
  let dividerElement: HTMLDivElement | null = null;

  let elevationPlotManager: ElevationPlotManager | null = null;
  let lineMeasurementController: ReturnType<typeof createLineMeasurementController> | null = null;

  /**
   * React to horizontal pane width updates from the splitter controller.
   * @param width Current width of the right-hand pane in pixels.
   */
  function handleRightPaneWidthChange(width: number): void {
    rightPaneWidth = width;
    elevationPlotManager?.resize();
  }

  const paneController = new HorizontalPaneController({
    onWidthChange: handleRightPaneWidthChange,
  });

  let rightPaneWidth = paneController.getRightWidth();

  const drawingController = new DrawingController({
    onLineChange: (coordinates, isFinal) => {
      lineMeasurementController?.updateLine(coordinates, isFinal);
    },
    onDrawingActivated: () => {
      elevationSection?.scrollIntoView({ behavior: "smooth", block: "start" });
      if (map) {
        paintController.reset(map);
      }
    },
    updateLineSources: (mapInstance, coordinates) => {
      updateDrawSources(mapInstance, coordinates);
    },
  });
  const paintController = new PaintController({
    brushRadius: 12,
    onPaintActivated: (mapInstance) => {
      drawingController.clearOverlay(mapInstance);
      highlightDrawPoint(mapInstance, null);
      volumeSection?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  });

  let highResAvailability = getAvailableHighResLayers(INITIAL_ZOOM);
  let zoomInMessageVisible = true;
  let parcelZoomMessageVisible = true;

  let lastClickedParcel: ParcelInfo | null = null;
  let lastClickedCoordinates: [number, number] | null = null;

  let baseLayer: BaseLayerId = "basic";
  let baseLayerOpacity = 1;
  let showBaseLayerContours = true;
  let hillshadeContoursVisible = false;

  let showParcels = false;

  let ladderLayer: LadderLayerId = "none";
  let showGullyProbability = false;
  let showGullyLines = false;

  let showElevationContours = false;
  let fillElevationContourPolygons = true;

  let userDrawToggle = false;
  let shiftDown = false;
  $: drawEnabled = userDrawToggle || shiftDown;
  let userPaintToggle = false;
  let controlOrCommandDown = false;
  $: paintEnabled = (userPaintToggle || controlOrCommandDown) && !drawEnabled;

  const googleMapsBaseUrl = "https://www.google.com/maps?q=";
  let googleMapsLink = "";
  let formattedCoordinates = "";

  let mapMouseDownHandler: ((event: maplibregl.MapMouseEvent) => void) | null = null;
  let mapMouseMoveHandler: ((event: maplibregl.MapMouseEvent) => void) | null = null;
  let mapMouseUpHandler: ((event: maplibregl.MapMouseEvent) => void) | null = null;
  let mapContextMenuHandler: ((event: MouseEvent) => void) | null = null;

  function handleWindowPointerMove(event: PointerEvent): void {
    if (activeDividerPointerId === null || event.pointerId !== activeDividerPointerId) {
      return;
    }
    paneController.handleDrag(event);
  }

  function handleWindowPointerUp(event: PointerEvent): void {
    if (activeDividerPointerId === null || event.pointerId !== activeDividerPointerId) {
      return;
    }
    if (dividerElement?.hasPointerCapture(event.pointerId)) {
      dividerElement.releasePointerCapture(event.pointerId);
    }
    activeDividerPointerId = null;
    paneController.stopDrag();
  }

  function handleWindowPointerCancel(event: PointerEvent): void {
    if (activeDividerPointerId === null || event.pointerId !== activeDividerPointerId) {
      return;
    }
    if (dividerElement?.hasPointerCapture(event.pointerId)) {
      dividerElement.releasePointerCapture(event.pointerId);
    }
    activeDividerPointerId = null;
    paneController.stopDrag();
  }

  function handleWindowBlur(): void {
    if (shiftDown) {
      shiftDown = false;
      drawingController.setShiftDown(false, map);
    }
    if (controlOrCommandDown) {
      controlOrCommandDown = false;
      paintController.setModifierEnabled(false, map);
    }
  }

  let leftPaneWidthCss = "";
  $: leftPaneWidthCss = `calc(100vw - 10px - ${rightPaneWidth}px)`;
  $: hillshadeContoursVisible = baseLayer === "hillshade_greyscale" && showBaseLayerContours;

  let activeDividerPointerId: number | null = null;

  /** Initialise controllers and global listeners when the component mounts. */
  onMount(() => {
    elevationPlotManager = new ElevationPlotManager({
      container: elevationPlotContainer,
      elevationPlot: elevationPlotElement,
      differencePlot: elevationDifferenceElement,
      warningBanner: lineTooLongBanner,
      onCursorMove: handlePlotCursorMove,
      createPlot: (element, config, data) => new uPlot(config, data, element),
    });
    elevationPlotManager.initialize();

    lineMeasurementController = createLineMeasurementController({ plotManager: elevationPlotManager });

    window.addEventListener("pointermove", handleWindowPointerMove);
    window.addEventListener("pointerup", handleWindowPointerUp);
    window.addEventListener("pointercancel", handleWindowPointerCancel);
    window.addEventListener("keydown", handleWindowKeydown);
    window.addEventListener("keyup", handleWindowKeyup);
    window.addEventListener("blur", handleWindowBlur);

    return () => {
      if (activeDividerPointerId !== null && dividerElement?.hasPointerCapture(activeDividerPointerId)) {
        dividerElement.releasePointerCapture(activeDividerPointerId);
      }
      activeDividerPointerId = null;

      window.removeEventListener("pointermove", handleWindowPointerMove);
      window.removeEventListener("pointerup", handleWindowPointerUp);
      window.removeEventListener("pointercancel", handleWindowPointerCancel);
      window.removeEventListener("keydown", handleWindowKeydown);
      window.removeEventListener("keyup", handleWindowKeyup);
      window.removeEventListener("blur", handleWindowBlur);
      elevationPlotManager?.destroy();
      if (map) {
        paintController.reset(map);
      }
      if (map && mapMouseDownHandler) {
        map.off("mousedown", mapMouseDownHandler);
      }
      if (map && mapMouseMoveHandler) {
        map.off("mousemove", mapMouseMoveHandler);
      }
      if (map && mapMouseUpHandler) {
        map.off("mouseup", mapMouseUpHandler);
      }
      if (map && mapContextMenuHandler) {
        map.getContainer().removeEventListener("contextmenu", mapContextMenuHandler);
      }
    };
  });

  /**
   * Enable drawing while the shift key is pressed.
   * @param event Keyboard event dispatched on window.
   */
  function handleWindowKeydown(event: KeyboardEvent): void {
    if (event.key === "Shift" && !shiftDown) {
      shiftDown = true;
      drawingController.setShiftDown(true, map);
    }
    if ((event.key === "Control" || event.key === "Meta") && !controlOrCommandDown) {
      controlOrCommandDown = true;
      paintController.setModifierEnabled(true, map);
    }
  }

  /**
   * Disable temporary drawing once the shift key is released.
   * @param event Keyboard event dispatched on window.
   */
  function handleWindowKeyup(event: KeyboardEvent): void {
    if (event.key === "Shift" && shiftDown) {
      shiftDown = false;
      drawingController.setShiftDown(false, map);
    }
    if ((event.key === "Control" || event.key === "Meta") && controlOrCommandDown) {
      controlOrCommandDown = false;
      paintController.setModifierEnabled(false, map);
    }
  }

  /**
   * Sync draw-mode checkbox state with the controller.
   * @param event Change event from the draw toggle checkbox.
   */
  function handleDrawToggleChange(event: Event): void {
    const target = event.currentTarget as HTMLInputElement;
    userDrawToggle = target.checked;
    drawingController.setUserToggle(userDrawToggle, map);
  }

  /**
   * Sync paint-mode checkbox state with the controller.
   * @param event Change event from the paint toggle checkbox.
   */
  function handlePaintToggleChange(event: Event): void {
    const target = event.currentTarget as HTMLInputElement;
    userPaintToggle = target.checked;
    paintController.setUserToggle(userPaintToggle, map);
  }

  /**
   * Initialise MapLibre specific listeners and layer state once the map loads.
   * @param loadedMap MapLibre instance provided by the component.
   */
  function handleMapLoad(loadedMap: maplibregl.Map): void {
    map = loadedMap;
    map.boxZoom.disable();
    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();
    map.setPitch(0);
    map.setBearing(0);

    highResAvailability = getAvailableHighResLayers(map.getZoom());
    if (baseLayer !== "basic" && !highResAvailability[baseLayer]) {
      baseLayer = "basic";
    }
    parcelZoomMessageVisible = map.getZoom() < 14;

    mapMouseDownHandler = (event) => {
      drawingController.handleMouseDown(map!, event);
      paintController.handleMouseDown(map!, event);
    };
    mapMouseMoveHandler = (event) => {
      drawingController.handleMouseMove(map!, event);
      paintController.handleMouseMove(map!, event);
    };
    mapMouseUpHandler = () => {
      paintController.handleMouseUp(map!);
    };
    mapContextMenuHandler = (event) => {
      if (event.ctrlKey || event.metaKey || paintEnabled) {
        event.preventDefault();
      }
    };

    map.on("mousedown", mapMouseDownHandler);
    map.on("mousemove", mapMouseMoveHandler);
    map.on("mouseup", mapMouseUpHandler);
    map.getContainer().addEventListener("contextmenu", mapContextMenuHandler);

    applyCurrentLayerState();
  }

  function handleFlyTo(item: maplibregl.FlyToOptions) {
    if (!map) {
      return;
    }

    map.flyTo(item);
  }

  /** Apply the current base layer and overlay selections to the map instance. */
  function applyCurrentLayerState(): void {
    if (!map) {
      return;
    }

    setBaseLayer(map, baseLayer);
    setBaseLayerTransparency(map, baseLayerOpacity);
    setContourVisibility(map, hillshadeContoursVisible);
    setLadderLayer(map, ladderLayer);
    setElevationDifferenceContours(map, {
      showContours: showElevationContours,
      showFill: fillElevationContourPolygons,
    });
    setLayerVisibility("parcels_outline", showParcels);
    setLayerVisibility("parcels", showParcels);
    setLayerVisibility("gully_detection_pass2", showGullyProbability);
    setLayerVisibility("gully_detection_pass3_outline", showGullyLines);
    setLayerVisibility("gully_detection_pass3", showGullyLines);
  }

  /**
   * Keep layer availability in sync with the current zoom level.
   * @param event Map zoom event.
   */
  function handleMapZoom(event: MapZoomEvent): void {
    const zoomLevel = event.target.getZoom();
    highResAvailability = getAvailableHighResLayers(zoomLevel);
    if (baseLayer !== "basic" && !highResAvailability[baseLayer]) {
      baseLayer = "basic";
    }
    parcelZoomMessageVisible = zoomLevel < 14;
  }

  /**
   * Capture and display parcel details and coordinates for the clicked location.
   * @param event Map click event.
   */
  function handleMapClick(event: maplibregl.MapMouseEvent): void {
    const { lng, lat } = event.lngLat;
    lastClickedCoordinates = [lng, lat];

    if (!map) {
      lastClickedParcel = null;
      return;
    }

    const features = map.queryRenderedFeatures(event.point, {
      layers: ["parcels-filled"],
    });

    if (!features.length || !features[0].properties) {
      lastClickedParcel = null;
      return;
    }

    const properties = features[0].properties as ParcelInfo;
    lastClickedParcel = {
      parcel: ensureString(properties.parcel),
      address: ensureString(properties.address),
      city: ensureString(properties.city),
      type: ensureString(properties.type),
      description: ensureString(properties.description),
    };
  }

  /**
   * Normalise empty string values read from feature properties.
   * @param value Property value from MapLibre.
   * @returns A trimmed string when present, otherwise undefined.
   */
  function ensureString(value: unknown): string | undefined {
    return typeof value === "string" && value.trim().length > 0 ? value : undefined;
  }

  /**
   * Highlight the nearest drawn point when users hover the elevation plots.
   * @param index Index reported by the plot cursor.
   */
  function handlePlotCursorMove(index: number | null): void {
    if (!map) {
      return;
    }

    if (index === null) {
      highlightDrawPoint(map, null);
      return;
    }

    const points = drawingController.getPoints();
    if (index < points.length) {
      highlightDrawPoint(map, points[index]);
    }
  }

  /**
   * Convenience wrapper to flip layer visibility flags via MapLibre.
   * @param layerId Layer identifier.
   * @param visible Desired visibility.
   */
  function setLayerVisibility(layerId: string, visible: boolean): void {
    if (!map) {
      return;
    }
    map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
  }

  /**
   * Format numbers for display as longitude/latitude pairs.
   * @param value Numeric coordinate value.
   * @returns A fixed-length coordinate string.
   */
  function formatCoordinate(value: number): string {
    return value.toFixed(6);
  }

  /**
   * Begin tracking pointer-based drag events for the divider and capture the pointer.
   * @param event Pointer event triggered on the divider.
   */
  function handleDividerPointerDown(event: PointerEvent): void {
    event.preventDefault();
    activeDividerPointerId = event.pointerId;
    dividerElement?.setPointerCapture(event.pointerId);
    paneController.startDrag();
    paneController.handleDrag(event);
  }

  $: if (map) {
    setBaseLayer(map, baseLayer);
  }

  $: if (map) {
    setBaseLayerTransparency(map, baseLayerOpacity);
  }

  $: if (map) {
    setContourVisibility(map, hillshadeContoursVisible);
  }

  $: if (map) {
    setLadderLayer(map, ladderLayer);
  }

  $: if (map) {
    setElevationDifferenceContours(map, {
      showContours: showElevationContours,
      showFill: fillElevationContourPolygons,
    });
  }

  $: if (map) {
    setLayerVisibility("parcels_outline", showParcels);
    setLayerVisibility("parcels", showParcels);
  }

  $: if (map) {
    setLayerVisibility("gully_detection_pass2", showGullyProbability);
  }

  $: if (map) {
    setLayerVisibility("gully_detection_pass3_outline", showGullyLines);
    setLayerVisibility("gully_detection_pass3", showGullyLines);
  }

  $: if (map) {
    drawingController.setUserToggle(userDrawToggle, map);
  }

  $: if (map) {
    drawingController.setShiftDown(shiftDown, map);
  }

  $: paintController.setLineDrawingActive(drawEnabled);

  $: if (map) {
    paintController.setUserToggle(userPaintToggle, map);
  }

  $: if (map) {
    paintController.setModifierEnabled(controlOrCommandDown, map);
  }

  $: zoomInMessageVisible = !Object.values(highResAvailability).every(
    (available) => available,
  );

  $: googleMapsLink = lastClickedCoordinates
    ? `${googleMapsBaseUrl}${lastClickedCoordinates[1]},${lastClickedCoordinates[0]}`
    : "";

  $: formattedCoordinates = lastClickedCoordinates
    ? `${formatCoordinate(lastClickedCoordinates[0])}, ${formatCoordinate(lastClickedCoordinates[1])}`
    : "";
</script>

<div class="whole-page">
  <div class="left-half" style={`width: ${leftPaneWidthCss};`}>
    <MapLibre
      center={[-122.88, 38.46]}
      zoom={9}
      class="map"
      standardControls
      style={mapStyleSpecification}
      onload={handleMapLoad}
      onzoom={handleMapZoom}
      onclick={handleMapClick}
    />
    <SearchBox onSelect={handleFlyTo} />
  </div>
  <div
    class="divider"
    role="separator"
    aria-orientation="vertical"
    aria-label="Resize panels"
    bind:this={dividerElement}
    on:pointerdown={handleDividerPointerDown}
  ></div>
  <div class="right-half" style={`width: ${rightPaneWidth}px;`}>
    <div style="text-align: right; margin-bottom: -5px;">
      <a href="https://oaec.org/" target="_blank" aria-label="Occidental Arts and Ecology Center">
        <img src="oaec-logo.png" width="150" alt="Occidental Arts and Ecology Center" style="display: inline-block; margin-right: 15px;" />
      </a>
      <a href="https://datascience.uchicago.edu/" target="_blank" aria-label="University of Chicago Data Science Institute">
        <img src="built-by-dsi.png" width="150" alt="University of Chicago Data Science Institute" style="display: inline-block; vertical-align: top;" />
      </a>
    </div>
    <div>
      <div class="group">
        <h1 style="margin-top: 0px;">Base layer</h1>
        <div>
          <div style="display: flex; width: 100%;">
            <label for="baselayer-slider" style="white-space: nowrap;">Hidden</label>
            <input
              id="baselayer-slider"
              type="range"
              min="0"
              max="1"
              step="0.1"
              bind:value={baseLayerOpacity}
              style="flex: 1;"
            />
            <label for="baselayer-slider" style="white-space: nowrap;">Visible</label>
          </div>
        </div>
        <div>
          <label>
            <input type="radio" name="baselayer" value="basic" bind:group={baseLayer} />
            Basic street map with topography
          </label>
          (<a href="https://github.com/nst-guide/osm-liberty-topo" target="_blank">from here</a>)
        </div>
        <div>
          <label
            for="baselayer-aerial-2013"
            class:disabled={!highResAvailability.aerial_2013}
          >
            <input
              id="baselayer-aerial-2013"
              type="radio"
              name="baselayer"
              value="aerial_2013"
              bind:group={baseLayer}
              disabled={!highResAvailability.aerial_2013}
            />
            2013 aerial photography
          </label>
          (<a href="https://www.arcgis.com/apps/mapviewer/index.html?url=https://socogis.sonomacounty.ca.gov/image/rest/services/Rasters/Ortho_SoCo_SonomaVeg_2013_WM/ImageServer&source=sd" target="_blank">Sonoma GIS</a>,
          <a href="https://www.arcgis.com/home/item.html?id=a5fc12e9c4324663bafde942a7d1e1d3" target="_blank">through Esri</a>)
        </div>
        <div>
          <label
            for="baselayer-aerial-2021"
            class:disabled={!highResAvailability.aerial_2021}
          >
            <input
              id="baselayer-aerial-2021"
              type="radio"
              name="baselayer"
              value="aerial_2021"
              bind:group={baseLayer}
              disabled={!highResAvailability.aerial_2021}
            />
            2021 aerial photography
          </label>
          (<a href="https://gis.sonomacounty.ca.gov/datasets/dc026cbfb9884d51a65dae1846bf76a5/explore?location=38.472153%2C-122.943650%2C10.18" target="_blank">Sonoma GIS</a>,
          <a href="https://www.arcgis.com/home/item.html?id=0c361a688a5a453487021132c878e870" target="_blank">through Esri</a>)
        </div>
        <div>
          <label class:disabled={!highResAvailability.hillshade_greyscale}>
            <input
              type="radio"
              name="baselayer"
              value="hillshade_greyscale"
              bind:group={baseLayer}
              disabled={!highResAvailability.hillshade_greyscale}
            />
            2022 hillshade
          </label>
          (page 9 of <a href="https://tukmangeospatial.egnyte.com/dl/ADWSBBL7ac" target="_blank">LIDAR derivatives</a>)
        </div>
        <div class="indent">
          <label>
            <input type="checkbox" bind:checked={showBaseLayerContours} />
            ... with 10 m contours
          </label>
        </div>
        <div>
          <label class:disabled={!highResAvailability.hillshade_color_enhanced}>
            <input
              type="radio"
              name="baselayer"
              value="hillshade_color_enhanced"
              bind:group={baseLayer}
              disabled={!highResAvailability.hillshade_color_enhanced}
            />
            2022 color-enhanced hillshade
          </label>
          (<a href="https://landscapearchaeology.org/2021/texture-shading/" target="_blank">fractional-Laplacian sharpened</a> overlay)
        </div>
        {#if zoomInMessageVisible}
          <div class="indent" style="margin-top: 0.5em">
            (Zoom in to enable missing baselayers.)
          </div>
        {/if}
      </div>
      <div class="group">
        <h1>Land ownership</h1>
        <div>
          <label>
            <input type="checkbox" bind:checked={showParcels} />
            Land ownership boundaries
          </label>
          (<a href="https://gis.sonomacounty.ca.gov/maps/4b231e8ffbac47abb9a78296e550ffa1" target="_blank">source</a>)
        </div>
      </div>
      <div class="group">
        <div style="margin-left: 11px;">
          Last clicked in{#if parcelZoomMessageVisible}<span>&nbsp;(zoom in to enable)</span>{/if}:
        </div>
        <div style="min-height: 1em; margin: 0px 5px 5px 5px; padding: 5px; border: 1px solid gray;">
          {#if lastClickedParcel}
            {#if lastClickedParcel.parcel}
              <b>Parcel ID (APN):</b> {lastClickedParcel.parcel}<br>
            {/if}
            {#if lastClickedParcel.address}
              <b>Address:</b> {lastClickedParcel.address}
              {#if lastClickedParcel.city}, {lastClickedParcel.city}{/if}<br>
            {/if}
            {#if lastClickedParcel.type}{lastClickedParcel.type}{/if}
            {#if lastClickedParcel.type && lastClickedParcel.description}; {/if}
            {#if lastClickedParcel.description}{lastClickedParcel.description}{/if}
          {/if}
        </div>
        <div style="margin-left: 11px;">
          Last clicked longitude-latitude{#if lastClickedCoordinates}<span>, and <a href={googleMapsLink} target="_blank">link to Google Maps</a></span>{/if}:
        </div>
        <div style="height: 1em; margin: 0px 5px 5px 5px; padding: 5px; border: 1px solid gray; overflow: hidden;">
          {#if formattedCoordinates}
            {formattedCoordinates}
          {/if}
        </div>
      </div>
      <div class="group">
        <h1>Fire hazard</h1>
        <div>
          <label>
            <input type="radio" name="ladderlayer" value="none" bind:group={ladderLayer} />
            Hide ladder fuel proxies
          </label>
        </div>
        <div>
          <label>
            <input type="radio" name="ladderlayer" value="4m" bind:group={ladderLayer} />
            (material in 1‒4 m) / (material in 0‒4 m)
          </label>
        </div>
        <div>
          <label>
            <input type="radio" name="ladderlayer" value="8m" bind:group={ladderLayer} />
            (material in 1‒8 m) / (material in 0‒8 m)
          </label>
        </div>
        <div class="indent">
          (See page 9 of <a href="https://tukmangeospatial.egnyte.com/dl/ADWSBBL7ac" target="_blank">LIDAR derivatives</a>)
        </div>
      </div>
      <div class="group">
        <h1>Gullies</h1>
        <div>
          <label>
            <input type="checkbox" bind:checked={showGullyProbability} />
            Gully detection probability
          </label>
        </div>
        <div>
          <label>
            <input type="checkbox" bind:checked={showGullyLines} />
            Gully paths as lines
          </label>
        </div>
      </div>
      <div class="group">
        <h1>Erosion</h1>
        <div>
          <label>
            <input type="checkbox" bind:checked={showElevationContours} />
            2013-2022 elevation difference contours
          </label>
        </div>
        <div class="indent">
          (1/3 meter spacing,
          <span style="vertical-align: 0.1em; display: inline-block; width: 1em; height: 1em;">
            <svg width="1em" height="1em" viewBox="0 0 24 24" style="display: inline; vertical-align: middle;" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="10" stroke="#9d3bff" stroke-width="2" fill="none"/>
              <circle cx="12" cy="12" r="5" stroke="#9d3bff" stroke-width="2" fill="none"/>
            </svg>
          </span>
          erosion,
          <span style="vertical-align: 0.1em; display: inline-block; width: 1em; height: 1em;">
            <svg width="1em" height="1em" viewBox="0 0 24 24" style="display: inline; vertical-align: middle;" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="10" stroke="#ff9100" stroke-width="2" fill="none"/>
              <circle cx="12" cy="12" r="5" stroke="#ff9100" stroke-width="2" fill="none"/>
            </svg>
          </span>
          deposition)
        </div>
        <div class="indent">
          <label>
            <input type="checkbox" bind:checked={fillElevationContourPolygons} />
            ...and fill in the polygons
          </label>
        </div>
      </div>
      <div class="group">
        <h1 bind:this={volumeSection}>Volume of erosion</h1>
        <div>
          <label for="paint-toggle" class:disabled={drawEnabled}>
            <input
              id="paint-toggle"
              type="checkbox"
              checked={paintEnabled}
              on:change={handlePaintToggleChange}
              disabled={drawEnabled}
            />
            Paint region instead of moving map
          </label>
        </div>
        <div class="indent">
          (holding the <b>control</b> or <b>command</b> key temporarily enables this paintbrush)
        </div>
      </div>
      <div class="group" bind:this={elevationSection}>
        <h1>Elevation along line</h1>
        <div>
          <label for="draw-toggle">
            <input
              id="draw-toggle"
              type="checkbox"
              checked={drawEnabled}
              on:change={handleDrawToggleChange}
            />
            Draw line instead of moving map
          </label>
        </div>
        <div class="indent">
          (holding the <b>shift</b> key temporarily enables this; <b>two clicks</b> for a straight line and <b>drag</b> for a curve)
        </div>
      </div>
      <div class="group">
        <div
          bind:this={lineTooLongBanner}
          style="color: magenta; font-weight: bold; display: none;"
        >
          Line is too long to measure!
        </div>
      </div>
      <div bind:this={elevationPlotContainer}>
        <div bind:this={elevationPlotElement} style="visibility: hidden;"></div>
        <div bind:this={elevationDifferenceElement} style="visibility: hidden;"></div>
      </div>
      <div style="height: 100px;"></div>
    </div>
  </div>
</div>
