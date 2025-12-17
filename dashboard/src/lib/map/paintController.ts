/**
 * Paintbrush controller that renders temporary strokes onto a MapLibre canvas source.
 * The painted overlay is intentionally transient and cleared whenever interactions end
 * or the map begins moving. Area is tracked in a mask alongside the visible canvas.
 */
import type { CanvasSource, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { getPreciseDistance } from "geolib";
import { getTile, pixelIndex, tileIndex } from "../elevation/elevationTiles";

type Coordinate = [number, number];

const PAINT_SOURCE_ID = "draw-paint";
const PAINT_LAYER_ID = "draw-paint-layer";

export interface PaintControllerOptions {
  brushRadius: number;
  onPaintActivated?: (map: MapLibreMap) => void;
  onPaintAreaChange?: (areaMeters: number | null) => void;
  onPaintVolumeChange?: (volumeMetersCubed: number | null) => void;
  onPaintVolumePendingChange?: (pending: boolean) => void;
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
  private mask: Uint8Array | null = null;
  private maskWidth = 0;
  private maskHeight = 0;
  private paintedPixelCount = 0;
  private areaPerPixelMeters: number | null = null;
  private maskMinX: number | null = null;
  private maskMinY: number | null = null;
  private maskMaxX: number | null = null;
  private maskMaxY: number | null = null;
  private volumeComputationToken = 0;

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
    this.paintedPixelCount = 0;
    this.areaPerPixelMeters = null;
    this.mask = null;
    this.maskWidth = 0;
    this.maskHeight = 0;
    this.maskMinX = null;
    this.maskMinY = null;
    this.maskMaxX = null;
    this.maskMaxY = null;
    this.options.onPaintAreaChange?.(null);
    this.options.onPaintVolumeChange?.(null);
    this.options.onPaintVolumePendingChange?.(false);
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
    if (this.areaPerPixelMeters === null) {
      this.areaPerPixelMeters = this.computeAreaPerPixel(map);
    }
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
    this.ensureMaskMatchesCanvas(this.canvas);

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

    this.updateMaskWithSegment(
      this.lastPoint[0] * dpr,
      this.lastPoint[1] * dpr,
      point[0] * dpr,
      point[1] * dpr,
      radius,
    );
    this.updateArea();
    this.triggerVolumeComputation(map);

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

    this.ensureMaskMatchesCanvas(this.canvas);
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

  /**
   * Ensure the paint mask matches the canvas size, clearing when resized.
   * @param canvas Canvas element used for painting.
   */
  private ensureMaskMatchesCanvas(canvas: HTMLCanvasElement): void {
    if (canvas.width === this.maskWidth && canvas.height === this.maskHeight && this.mask) {
      return;
    }
    this.maskWidth = canvas.width;
    this.maskHeight = canvas.height;
    this.mask = new Uint8Array(this.maskWidth * this.maskHeight);
    this.paintedPixelCount = 0;
    this.maskMinX = null;
    this.maskMinY = null;
    this.maskMaxX = null;
    this.maskMaxY = null;
    this.options.onPaintAreaChange?.(null);
    this.options.onPaintVolumeChange?.(null);
    this.options.onPaintVolumePendingChange?.(false);
  }

  /**
   * Update the area measurement based on painted pixels.
   */
  private updateArea(): void {
    if (this.areaPerPixelMeters === null) {
      return;
    }
    const area = this.paintedPixelCount * this.areaPerPixelMeters;
    this.options.onPaintAreaChange?.(area);
  }

  /**
   * Start an asynchronous volume computation for the current mask.
   */
  private triggerVolumeComputation(map: MapLibreMap): void {
    const currentToken = ++this.volumeComputationToken;
    this.options.onPaintVolumePendingChange?.(this.paintedPixelCount > 0);
    void this.computeVolume(map, currentToken);
  }

  /**
   * Compute volume by sampling elevation tiles under the painted mask.
   * @param map MapLibre instance.
   * @param token Token to discard stale computations.
   */
  private async computeVolume(map: MapLibreMap, token: number): Promise<void> {
    if (!this.mask || this.areaPerPixelMeters === null || this.paintedPixelCount === 0) {
      if (token === this.volumeComputationToken) {
        this.options.onPaintVolumeChange?.(null);
        this.options.onPaintVolumePendingChange?.(false);
      }
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    const minX = this.maskMinX ?? 0;
    const minY = this.maskMinY ?? 0;
    const maxX = this.maskMaxX ?? -1;
    const maxY = this.maskMaxY ?? -1;

    const tiles = new Map<
      string,
      {
        tileX: number;
        tileY: number;
        pixels: Array<[number, number]>;
        tile: ReturnType<typeof getTile>;
      }
    >();

    for (let y = minY; y <= maxY; y += 1) {
      for (let x = minX; x <= maxX; x += 1) {
        const idx = y * this.maskWidth + x;
        if (this.mask[idx] === 0) {
          continue;
        }
        const cssX = x / dpr;
        const cssY = y / dpr;
        const ll = map.unproject([cssX, cssY]);
        const [tileX, tileY] = tileIndex(ll.lng, ll.lat);
        const [px, py] = pixelIndex(ll.lng, ll.lat);
        const key = `${tileX}:${tileY}`;
        if (!tiles.has(key)) {
          tiles.set(key, { tileX, tileY, pixels: [], tile: getTile(tileX, tileY) });
        }
        tiles.get(key)!.pixels.push([px, py]);
      }
    }

    // Wait for tiles to be ready.
    while (
      token === this.volumeComputationToken
      && Array.from(tiles.values()).some((entry) => entry.tile.waiting())
    ) {
      await this.delay(100);
    }
    if (token !== this.volumeComputationToken) {
      return;
    }

    let volume = 0;
    for (const entry of tiles.values()) {
      const tile = entry.tile;
      for (const [px, py] of entry.pixels) {
        const v22 = tile.simple2022(px, py);
        const v13 = tile.simple2013(px, py);
        if (v22 === null || v13 === null) {
          continue;
        }
        volume += (v22 - v13) * this.areaPerPixelMeters;
      }
    }

    if (token === this.volumeComputationToken) {
      this.options.onPaintVolumeChange?.(volume);
      this.options.onPaintVolumePendingChange?.(false);
    }
  }

  /**
   * Draw a thickened segment into the mask by stamping circles along the path.
   */
  private updateMaskWithSegment(ax: number, ay: number, bx: number, by: number, radius: number): void {
    if (!this.mask) {
      return;
    }
    const dx = bx - ax;
    const dy = by - ay;
    const length = Math.hypot(dx, dy);
    const step = Math.max(1, radius / 2);
    const steps = Math.max(1, Math.ceil(length / step));
    for (let i = 0; i <= steps; i += 1) {
      const t = steps === 0 ? 0 : i / steps;
      const px = ax + dx * t;
      const py = ay + dy * t;
      this.stampCircle(px, py, radius);
    }
  }

  /**
   * Stamp a filled circle into the mask and count newly painted pixels.
   */
  private stampCircle(cx: number, cy: number, radius: number): void {
    if (!this.mask) {
      return;
    }
    const r2 = radius * radius;
    const minX = Math.max(0, Math.floor(cx - radius));
    const maxX = Math.min(this.maskWidth - 1, Math.ceil(cx + radius));
    const minY = Math.max(0, Math.floor(cy - radius));
    const maxY = Math.min(this.maskHeight - 1, Math.ceil(cy + radius));

    for (let y = minY; y <= maxY; y += 1) {
      const dy = y - cy;
      for (let x = minX; x <= maxX; x += 1) {
        const dx = x - cx;
        if (dx * dx + dy * dy <= r2) {
          const idx = y * this.maskWidth + x;
          if (this.mask[idx] === 0) {
            this.mask[idx] = 1;
            this.paintedPixelCount += 1;
            this.maskMinX = this.maskMinX === null ? x : Math.min(this.maskMinX, x);
            this.maskMaxX = this.maskMaxX === null ? x : Math.max(this.maskMaxX, x);
            this.maskMinY = this.maskMinY === null ? y : Math.min(this.maskMinY, y);
            this.maskMaxY = this.maskMaxY === null ? y : Math.max(this.maskMaxY, y);
          }
        }
      }
    }
  }

  /**
   * Compute area per pixel in square meters using local map scale.
   */
  private computeAreaPerPixel(map: MapLibreMap): number {
    const ll00 = map.unproject([0, 0]);
    const ll10 = map.unproject([1, 0]);
    const ll01 = map.unproject([0, 1]);
    const metersX = getPreciseDistance(
      { latitude: ll00.lat, longitude: ll00.lng },
      { latitude: ll10.lat, longitude: ll10.lng },
      1e-8,  // accuracy
    );
    const metersY = getPreciseDistance(
      { latitude: ll00.lat, longitude: ll00.lng },
      { latitude: ll01.lat, longitude: ll01.lng },
      1e-8,  // accuracy
    );
    return metersX * metersY;
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }
}
