/**
 * Paintbrush controller that renders temporary strokes onto a MapLibre canvas source.
 * The painted overlay is intentionally transient and cleared whenever interactions end
 * or the map begins moving.
 */
import type { CanvasSource, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";

type Coordinate = [number, number];

const PAINT_SOURCE_ID = "draw-paint";
const PAINT_LAYER_ID = "draw-paint-layer";

export interface PaintControllerOptions {
  brushRadius: number;
  onPaintActivated?: (map: MapLibreMap) => void;
}

export class PaintController {
  private readonly options: PaintControllerOptions;
  private userToggleEnabled = false;
  private modifierEnabled = false;
  private lineDrawingActive = false;
  private isPainting = false;
  private lastPoint: Coordinate | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private context: CanvasRenderingContext2D | null = null;
  private moveListener: (() => void) | null = null;

  constructor(options: PaintControllerOptions) {
    this.options = options;
  }

  /**
   * Respond to mouse down events and begin a paint stroke when enabled.
   * @param map MapLibre instance.
   * @param event Mouse event with pixel coordinates.
   */
  handleMouseDown(map: MapLibreMap, event: MapMouseEvent): void {
    if (!this.isEnabled() || event.originalEvent.button !== 0) {
      return;
    }

    this.startPainting(map, event);
  }

  /**
   * Update the stroke while the mouse moves.
   * @param map MapLibre instance.
   * @param event Mouse move event.
   */
  handleMouseMove(map: MapLibreMap, event: MapMouseEvent): void {
    if (!this.isPainting) {
      return;
    }

    this.paintAt(map, [event.point.x, event.point.y]);
  }

  /**
   * Finish the current stroke.
   * @param map MapLibre instance.
   */
  handleMouseUp(map: MapLibreMap): void {
    if (!this.isPainting) {
      return;
    }
    this.stopPainting(map);
  }

  /**
   * Apply the explicit paint-mode toggle from the UI.
   * @param enabled Whether the user enabled painting.
   * @param map Optional map instance for clearing state.
   */
  setUserToggle(enabled: boolean, map: MapLibreMap | null): void {
    this.userToggleEnabled = enabled;
    this.stopPaintingIfInactive(map);
  }

  /**
   * Track whether the control/command modifier is active.
   * @param enabled True when the modifier is pressed.
   * @param map Optional map instance for clearing state.
   */
  setModifierEnabled(enabled: boolean, map: MapLibreMap | null): void {
    this.modifierEnabled = enabled;
    this.stopPaintingIfInactive(map);
  }

  /**
   * Record whether line drawing is active, which takes priority over painting input
   * (but should not clear existing paint).
   * @param active True when line drawing is enabled.
   */
  setLineDrawingActive(active: boolean): void {
    this.lineDrawingActive = active;
  }

  /**
   * Clear painted overlays and tear down temporary listeners.
   * @param map MapLibre instance, when available.
   */
  reset(map: MapLibreMap | null): void {
    this.isPainting = false;
    this.lastPoint = null;
    if (map) {
      if (this.moveListener) {
        map.off("movestart", this.moveListener);
      }
      map.dragPan.enable();
      this.removePaintLayer(map);
    }
    this.moveListener = null;
    this.context = null;
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
    this.canvas = null;
  }

  /**
   * Determine whether the paintbrush should intercept input.
   * @returns True when painting is enabled and line drawing is inactive.
   */
  private isEnabled(): boolean {
    return (this.userToggleEnabled || this.modifierEnabled) && !this.lineDrawingActive;
  }

  /**
   * Initialise painting state and CanvasSource wiring.
   * @param map MapLibre instance.
   * @param event Mouse down event that started the stroke.
   */
  private startPainting(map: MapLibreMap, event: MapMouseEvent): void {
    this.isPainting = true;
    this.lastPoint = [event.point.x, event.point.y];
    map.dragPan.disable();
    this.options.onPaintActivated?.(map);
    this.setupCanvas(map);
    this.paintAt(map, this.lastPoint);

    const handleMoveStart = (): void => {
      this.reset(map);
    };
    this.moveListener = handleMoveStart;
    map.on("movestart", handleMoveStart);
  }

  /**
   * Draw a segment of the current stroke onto the canvas.
   * @param map MapLibre instance.
   * @param point Pixel coordinate relative to the map viewport.
   */
  private paintAt(map: MapLibreMap, point: Coordinate): void {
    if (!this.context || !this.canvas || !this.lastPoint) {
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    const radius = this.options.brushRadius * dpr;

    this.context.lineCap = "round";
    this.context.lineJoin = "round";
    this.context.strokeStyle = "rgba(255, 0, 255, 1)";
    this.context.fillStyle = "rgba(255, 0, 255, 1)";
    this.context.lineWidth = radius * 2;

    this.context.beginPath();
    this.context.moveTo(this.lastPoint[0] * dpr, this.lastPoint[1] * dpr);
    this.context.lineTo(point[0] * dpr, point[1] * dpr);
    this.context.stroke();
    this.context.closePath();

    this.lastPoint = point;
    this.refreshCanvasSource(map);
  }

  /**
   * Finalise a stroke and re-enable map panning.
   * @param map MapLibre instance.
   */
  private stopPainting(map: MapLibreMap): void {
    this.isPainting = false;
    this.lastPoint = null;
    map.dragPan.enable();
  }

  /**
   * End an active stroke when painting is no longer enabled, without clearing overlays.
   * @param map MapLibre instance.
   */
  private stopPaintingIfInactive(map: MapLibreMap | null): void {
    if (this.isEnabled() || !map) {
      return;
    }
    this.stopPainting(map);
  }

  /**
   * Ensure the canvas element and CanvasSource/layer exist for painting.
   * @param map MapLibre instance.
   */
  private setupCanvas(map: MapLibreMap): void {
    const container = map.getContainer();
    const { clientWidth, clientHeight } = container;
    const dpr = window.devicePixelRatio || 1;
    const targetWidth = clientWidth * dpr;
    const targetHeight = clientHeight * dpr;
    const isNewCanvas = !this.canvas;

    if (!this.canvas) {
      this.canvas = document.createElement("canvas");
      this.canvas.id = "paintbrush-canvas";
      this.canvas.style.position = "absolute";
      this.canvas.style.top = "0";
      this.canvas.style.left = "0";
      this.canvas.style.width = `${clientWidth}px`;
      this.canvas.style.height = `${clientHeight}px`;
      this.canvas.style.pointerEvents = "none";
      this.canvas.style.opacity = "0";
      this.canvas.addEventListener("contextmenu", (event) => {
        event.preventDefault();
      });
      container.appendChild(this.canvas);
    }

    const sizeChanged = this.canvas.width !== targetWidth || this.canvas.height !== targetHeight;
    if (sizeChanged) {
      this.canvas.width = targetWidth;
      this.canvas.height = targetHeight;
    }

    this.context = this.canvas.getContext("2d");
    if (!this.context) {
      return;
    }
    if (isNewCanvas || sizeChanged) {
      this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    const bounds = map.getBounds();
    const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
      [bounds.getWest(), bounds.getNorth()],
      [bounds.getEast(), bounds.getNorth()],
      [bounds.getEast(), bounds.getSouth()],
      [bounds.getWest(), bounds.getSouth()],
    ];

    if (!map.getSource(PAINT_SOURCE_ID)) {
      map.addSource(PAINT_SOURCE_ID, {
        type: "canvas",
        canvas: this.canvas,
        coordinates,
      });

      map.addLayer({
        id: PAINT_LAYER_ID,
        type: "raster",
        source: PAINT_SOURCE_ID,
        paint: {
          "raster-opacity": 1,
        },
      });
    } else {
      const source = map.getSource(PAINT_SOURCE_ID) as CanvasSource;
      source.setCoordinates(coordinates);
    }
  }

  /**
   * Push the latest canvas pixels into the MapLibre source.
   * @param map MapLibre instance.
   */
  private refreshCanvasSource(map: MapLibreMap): void {
    const source = map.getSource(PAINT_SOURCE_ID) as CanvasSource | undefined;
    source?.play?.();
  }

  /**
   * Tear down the paint source and layer.
   * @param map MapLibre instance.
   */
  private removePaintLayer(map: MapLibreMap): void {
    if (map.getLayer(PAINT_LAYER_ID)) {
      map.removeLayer(PAINT_LAYER_ID);
    }
    if (map.getSource(PAINT_SOURCE_ID)) {
      map.removeSource(PAINT_SOURCE_ID);
    }
  }
}
