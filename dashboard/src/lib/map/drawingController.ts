/**
 * State machine for managing freehand and straight-line drawing interactions on MapLibre.
 */
import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";

type Coordinate = [number, number];

export interface DrawingControllerOptions {
  onLineChange: (coordinates: Coordinate[], isFinal: boolean) => void;
  onDrawingActivated?: () => void;
  updateLineSources: (map: MapLibreMap, coordinates: Coordinate[]) => void;
}

type DrawState = "idle" | "freehand" | "awaiting-second-click";

export class DrawingController {
  private drawState: DrawState = "idle";
  private drawPoints: Coordinate[] = [];
  private userToggleEnabled = false;
  private shiftEnabled = false;
  private readonly options: DrawingControllerOptions;

  constructor(options: DrawingControllerOptions) {
    this.options = options;
  }

  /**
   * Determine whether drawing should intercept user input.
   * @returns True when drawing is enabled via toggle or shift key.
   */
  private isEnabled(): boolean {
    return this.userToggleEnabled || this.shiftEnabled;
  }

  /**
   * Handle the initial mouse down event, kicking off freehand or straight-line drawing.
   * @param map MapLibre instance receiving events.
   * @param event Mouse event with geographic data.
   */
  handleMouseDown(map: MapLibreMap, event: MapMouseEvent): void {
    if (!this.isEnabled() || event.originalEvent.button !== 0) {
      return;
    }

    if (this.drawState === "awaiting-second-click") {
      this.finishStraightLine(map, event);
      return;
    }

    let hasMoved = false;
    let isFirstEvent = true;

    /**
     * Respond to mouse move events while the button is held.
     * @param moveEvent Current mouse move event.
     */
    const moveListener = (moveEvent: MapMouseEvent): void => {
      if (!isFirstEvent && this.drawState === "idle") {
        detach();
        map.dragPan.enable();
        return;
      }
      isFirstEvent = false;

      hasMoved = true;
      if (this.drawState !== "freehand") {
        this.startFreehand(map, event);
      }
      this.updateFreehand(map, moveEvent);
    };

    /**
     * Handle the mouse up event to finalise freehand or begin straight-line drawing.
     * @param upEvent Final mouse event for this drag.
     */
    const upListener = (upEvent: MapMouseEvent): void => {
      isFirstEvent = false;

      detach();
      map.dragPan.enable();

      if (this.drawState === "freehand") {
        this.finishFreehand(map);
      } else if (!hasMoved) {
        this.startStraightLine(map, upEvent);
      } else {
        this.cancelDrawing(map);
      }
    };

    /** Remove temporary listeners once the drag completes. */
    function detach(): void {
      map.off("mousemove", moveListener);
      map.off("mouseup", upListener);
    }

    map.dragPan.disable();
    map.on("mousemove", moveListener);
    map.on("mouseup", upListener);
  }

  /**
   * Handle raw mouse move events emitted by MapLibre.
   * @param map MapLibre instance.
   * @param event Mouse event containing the pointer location.
   */
  handleMouseMove(map: MapLibreMap, event: MapMouseEvent): void {
    if (this.drawState === "awaiting-second-click") {
      this.updateStraightLine(map, event);
    }
  }

  /**
   * Set the explicit draw toggle state controlled via the UI.
   * @param enabled Whether drawing should stay enabled.
   * @param map Optional map reference used to clear drawn state.
   */
  setUserToggle(enabled: boolean, map: MapLibreMap | null): void {
    this.userToggleEnabled = enabled;
    if (!this.isEnabled()) {
      this.cancelDrawing(map);
    }
  }

  /**
   * Track whether the shift key modifier is active for temporary drawing.
   * @param isDown True when the shift key is pressed.
   * @param map Map for clearing drawing overlays.
   */
  setShiftDown(isDown: boolean, map: MapLibreMap | null): void {
    this.shiftEnabled = isDown;
    if (!this.isEnabled()) {
      this.cancelDrawing(map);
    }
  }

  /**
   * Begin a freehand interaction, anchoring the first point and notifying listeners.
   * @param map Map instance.
   * @param event Mouse event used to seed the polyline.
   */
  private startFreehand(map: MapLibreMap, event: MapMouseEvent): void {
    this.drawState = "freehand";
    this.drawPoints = [[event.lngLat.lng, event.lngLat.lat]];
    this.options.onDrawingActivated?.();
    this.updateSources(map);
  }

  /**
   * Append new points while freehand drawing and forward updates.
   * @param map Map instance.
   * @param event Mouse move event containing the new coordinate.
   */
  private updateFreehand(map: MapLibreMap, event: MapMouseEvent): void {
    if (this.drawState !== "freehand") {
      return;
    }

    const latestPoint: Coordinate = [event.lngLat.lng, event.lngLat.lat];
    const previousPoint = this.drawPoints[this.drawPoints.length - 1];
    if (!previousPoint || latestPoint[0] !== previousPoint[0] || latestPoint[1] !== previousPoint[1]) {
      this.drawPoints.push(latestPoint);
      this.updateSources(map);
      this.options.onLineChange([...this.drawPoints], false);
    }
  }

  /**
   * Finalise a freehand stroke and trigger the plot update.
   * @param map Map instance.
   */
  private finishFreehand(map: MapLibreMap): void {
    if (this.drawState === "freehand" && this.drawPoints.length > 1) {
      this.options.onLineChange([...this.drawPoints], true);
    }
    this.cancelDrawing(map);
  }

  /**
   * Start a straight-line drawing gesture by capturing the origin.
   * @param map Map instance.
   * @param event Mouse event containing the first coordinate.
   */
  private startStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    this.drawState = "awaiting-second-click";
    const point: Coordinate = [event.lngLat.lng, event.lngLat.lat];
    this.drawPoints = [point, point];
    this.options.onDrawingActivated?.();
    this.updateSources(map);
  }

  /**
   * Update the temporary second point for a straight-line gesture.
   * @param map Map instance.
   * @param event Mouse event containing the latest coordinate.
   */
  private updateStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    if (this.drawState !== "awaiting-second-click") {
      return;
    }
    this.drawPoints[this.drawPoints.length - 1] = [event.lngLat.lng, event.lngLat.lat];
    this.drawPoints = interpolatePoints(this.drawPoints);
    this.updateSources(map);
    this.options.onLineChange([...this.drawPoints], false);
  }

  /**
   * Finalise a straight-line, interpolating intermediate points for sampling.
   * @param map Map instance.
   * @param event Mouse event containing the end coordinate.
   */
  private finishStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    if (this.drawState !== "awaiting-second-click") {
      return;
    }
    this.drawPoints[this.drawPoints.length - 1] = [event.lngLat.lng, event.lngLat.lat];
    this.drawPoints = interpolatePoints(this.drawPoints);
    this.updateSources(map);
    this.options.onLineChange([...this.drawPoints], true);
    this.cancelDrawing(map);
  }

  /**
   * Reset controller state and clear the drawn polyline overlays.
   * @param map Map instance, when available.
   */
  cancelDrawing(map: MapLibreMap | null): void {
    this.drawState = "idle";
    if (map) {
      this.updateSources(map);
    }
  }

  /**
   * Update map sources responsible for rendering the draw overlay.
   * @param map Map instance.
   * @param coordinates Points to draw.
   */
  private updateSources(map: MapLibreMap): void {
    this.options.updateLineSources(map, this.drawPoints);
  }

  /**
   * Retrieve a copy of the current drawn coordinates.
   * @returns Cloned coordinate array.
   */
  getPoints(): Coordinate[] {
    return [...this.drawPoints];
  }
}

/**
 * Linearly interpolate between two coordinates to create a fixed number of segments.
 * @param coordinates Input coordinate pair.
 * @returns Interpolated coordinate list including the endpoints.
 */
function interpolatePoints(coordinates: Coordinate[]): Coordinate[] {
  const start = coordinates[0];
  const end = coordinates[coordinates.length - 1];
  if (!start || !end) {
    return coordinates;
  }

  const result: Coordinate[] = [];
  const segments = 100;

  for (let i = 0; i < segments; i += 1) {
    const t = i / (segments - 1);
    result.push([
      start[0] * (1 - t) + end[0] * t,
      start[1] * (1 - t) + end[1] * t,
    ]);
  }

  return result;
}
