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

export function createDrawingController(
  options: DrawingControllerOptions,
): DrawingController {
  let drawState: DrawState = "idle";
  let drawPoints: Coordinate[] = [];
  let userToggleEnabled = false;
  let shiftEnabled = false;

  function isEnabled(): boolean {
    return userToggleEnabled || shiftEnabled;
  }

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

    function detach(): void {
      map.off("mousemove", moveListener);
      map.off("mouseup", upListener);
    }

    map.dragPan.disable();
    map.on("mousemove", moveListener);
    map.on("mouseup", upListener);
  }

  function handleMouseMove(map: MapLibreMap, event: MapMouseEvent): void {
    if (drawState === "awaiting-second-click") {
      updateStraightLine(map, event);
    }
  }

  function setUserToggle(enabled: boolean, map: MapLibreMap | null): void {
    userToggleEnabled = enabled;
    if (!isEnabled()) {
      cancelDrawing(map);
    }
  }

  function setShiftDown(isDown: boolean, map: MapLibreMap | null): void {
    shiftEnabled = isDown;
    if (!isEnabled()) {
      cancelDrawing(map);
    }
  }

  function startFreehand(map: MapLibreMap, event: MapMouseEvent): void {
    drawState = "freehand";
    drawPoints = [[event.lngLat.lng, event.lngLat.lat]];
    options.onDrawingActivated?.();
    updateSources(map);
  }

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

  function finishFreehand(map: MapLibreMap): void {
    if (drawState === "freehand" && drawPoints.length > 1) {
      options.onLineChange([...drawPoints], true);
    }
    cancelDrawing(map);
  }

  function startStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    drawState = "awaiting-second-click";
    const point: Coordinate = [event.lngLat.lng, event.lngLat.lat];
    drawPoints = [point, point];
    options.onDrawingActivated?.();
    updateSources(map);
  }

  function updateStraightLine(map: MapLibreMap, event: MapMouseEvent): void {
    if (drawState !== "awaiting-second-click") {
      return;
    }
    drawPoints[drawPoints.length - 1] = [event.lngLat.lng, event.lngLat.lat];
    drawPoints = interpolatePoints(drawPoints);
    updateSources(map);
    options.onLineChange([...drawPoints], false);
  }

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

  function cancelDrawing(map: MapLibreMap | null): void {
    drawState = "idle";
    if (map) {
      updateSources(map);
    }
  }

  function updateSources(map: MapLibreMap): void {
    options.updateLineSources(map, drawPoints);
  }

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
