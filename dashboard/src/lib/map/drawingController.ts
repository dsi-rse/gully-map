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

export interface DrawingController {
  handleMouseDown: (map: MapLibreMap, event: MapMouseEvent) => void;
  handleMouseMove: (map: MapLibreMap, event: MapMouseEvent) => void;
  setUserToggle: (enabled: boolean, map: MapLibreMap | null) => void;
  setShiftDown: (isDown: boolean, map: MapLibreMap | null) => void;
  cancelDrawing: (map: MapLibreMap | null) => void;
  getPoints: () => Coordinate[];
}

/**
 * Create a drawing controller that coordinates map events, draw state, and plot updates.
 * @param options Handlers used to reflect draw state externally.
 * @returns A controller with event handlers and helpers for map drawing.
 */
export function createDrawingController(
  options: DrawingControllerOptions,
): DrawingController {
  let drawState: DrawState = "idle";
  let drawPoints: Coordinate[] = [];
  let userToggleEnabled = false;
  let shiftEnabled = false;

  /**
   * Determine whether drawing should intercept user input.
   * @returns True when drawing is enabled via toggle or shift key.
   */
  function isEnabled(): boolean {
    return userToggleEnabled || shiftEnabled;
  }

  /**
   * Handle the initial mouse down event, kicking off freehand or straight-line drawing.
   * @param map MapLibre instance receiving events.
   * @param event Mouse event with geographic data.
   */
  function handleMouseDown(map: MapLibreMap, event: MapMouseEvent): void {
    if (!isEnabled() || event.originalEvent.button !== 0) {
      return;
    }

    if (drawState === "awaiting-second-click") {
      finishStraightLine(map, event);
      return;
    }

    let hasMoved = false;
    let isFirstEvent = true;

    /**
     * Respond to mouse move events while the button is held.
     * @param moveEvent Current mouse move event.
     */
    const moveListener = (moveEvent: MapMouseEvent): void => {
      if (!isFirstEvent && drawState === "idle") {
        detach();
        map.dragPan.enable();
        return;
      }
      isFirstEvent = false;

      hasMoved = true;
      if (drawState !== "freehand") {
        startFreehand(map, event);
      }
      updateFreehand(map, moveEvent);
    };

    /**
     * Handle the mouse up event to finalise freehand or begin straight-line drawing.
     * @param upEvent Final mouse event for this drag.
     */
    const upListener = (upEvent: MapMouseEvent): void => {
      isFirstEvent = false;

      detach();
      map.dragPan.enable();

      if (drawState === "freehand") {
        finishFreehand(map);
      } else if (!hasMoved) {
        startStraightLine(map, upEvent);
      } else {
        cancelDrawing(map);
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
  function handleMouseMove(map: MapLibreMap, event: MapMouseEvent): void {
    if (drawState === "awaiting-second-click") {
      updateStraightLine(map, event);
    }
  }

  /**
   * Set the explicit draw toggle state controlled via the UI.
   * @param enabled Whether drawing should stay enabled.
   * @param map Optional map reference used to clear drawn state.
   */
  function setUserToggle(enabled: boolean, map: MapLibreMap | null): void {
    userToggleEnabled = enabled;
    if (!isEnabled()) {
      cancelDrawing(map);
    }
  }

  /**
   * Track whether the shift key modifier is active for temporary drawing.
   * @param isDown True when the shift key is pressed.
   * @param map Map for clearing drawing overlays.
   */
  function setShiftDown(isDown: boolean, map: MapLibreMap | null): void {
    shiftEnabled = isDown;
    if (!isEnabled()) {
      cancelDrawing(map);
    }
  }

  /**
   * Begin a freehand interaction, anchoring the first point and notifying listeners.
   * @param map Map instance.
   * @param event Mouse event used to seed the polyline.
   */
  function startFreehand(map: MapLibreMap, event: MapMouseEvent): void {
    drawState = "freehand";
    drawPoints = [[event.lngLat.lng, event.lngLat.lat]];
    options.onDrawingActivated?.();
    updateSources(map);
  }

  /**
   * Append new points while freehand drawing and forward updates.
   * @param map Map instance.
   * @param event Mouse move event containing the new coordinate.
   */
  function updateFreehand(map: MapLibreMap, event: MapMouseEvent): void {
    if (drawState !== "freehand") {
      return;
    }

    const latestPoint: Coordinate = [event.lngLat.lng, event.lngLat.lat];
    const previousPoint = drawPoints[drawPoints.length - 1];
    if (!previousPoint || latestPoint[0] !== previousPoint[0] || latestPoint[1] !== previousPoint[1]) {
      drawPoints.push(latestPoint);
      updateSources(map);
      options.onLineChange([...drawPoints], false);
    }
  }

  /**
   * Finalise a freehand stroke and trigger the plot update.
   * @param map Map instance.
   */
  function finishFreehand(map: MapLibreMap): void {
    if (drawState === "freehand" && drawPoints.length > 1) {
      options.onLineChange([...drawPoints], true);
    }
    cancelDrawing(map);
  }

  /**
   * Start a straight-line drawing gesture by capturing the origin.
   * @param map Map instance.
   * @param event Mouse event containing the first coordinate.
   */
  function startStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    drawState = "awaiting-second-click";
    const point: Coordinate = [event.lngLat.lng, event.lngLat.lat];
    drawPoints = [point, point];
    options.onDrawingActivated?.();
    updateSources(map);
  }

  /**
   * Update the temporary second point for a straight-line gesture.
   * @param map Map instance.
   * @param event Mouse event containing the latest coordinate.
   */
  function updateStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    if (drawState !== "awaiting-second-click") {
      return;
    }
    drawPoints[drawPoints.length - 1] = [event.lngLat.lng, event.lngLat.lat];
    drawPoints = interpolatePoints(drawPoints);
    updateSources(map);
    options.onLineChange([...drawPoints], false);
  }

  /**
   * Finalise a straight-line, interpolating intermediate points for sampling.
   * @param map Map instance.
   * @param event Mouse event containing the end coordinate.
   */
  function finishStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    if (drawState !== "awaiting-second-click") {
      return;
    }
    drawPoints[drawPoints.length - 1] = [event.lngLat.lng, event.lngLat.lat];
    drawPoints = interpolatePoints(drawPoints);
    updateSources(map);
    options.onLineChange([...drawPoints], true);
    cancelDrawing(map);
  }

  /**
   * Reset controller state and clear the drawn polyline overlays.
   * @param map Map instance, when available.
   */
  function cancelDrawing(map: MapLibreMap | null): void {
    drawState = "idle";
    if (map) {
      updateSources(map);
    }
  }

  /**
   * Update map sources responsible for rendering the draw overlay.
   * @param map Map instance.
   * @param coordinates Points to draw.
   */
  function updateSources(map: MapLibreMap): void {
    options.updateLineSources(map, drawPoints);
  }

  /**
   * Retrieve a copy of the current drawn coordinates.
   * @returns Cloned coordinate array.
   */
  function getPoints(): Coordinate[] {
    return [...drawPoints];
  }

  return {
    handleMouseDown,
    handleMouseMove,
    setUserToggle,
    setShiftDown,
    cancelDrawing,
    getPoints,
  };
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
