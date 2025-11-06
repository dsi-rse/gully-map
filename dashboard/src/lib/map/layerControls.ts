import type { Map as MapLibreMap } from "maplibre-gl";

export type BaseLayerId = "basic" | keyof typeof HIGH_RES_LAYERS;
export type LadderLayerId = "none" | "4m" | "8m";

export const HIGH_RES_LAYERS: Record<string, number> = {
  aerial_2013: 14,
  aerial_2021: 12,
  hillshade_greyscale: 9,
  hillshade_color_enhanced: 9,
};

const ELEVATION_CONTOUR_LAYERS = [
  "elevation_contours_outline",
  "elevation_contours_50",
  "elevation_contours_10",
  "elevation_contours_label",
];

const LADDER_LAYER_VISIBILITY: Record<LadderLayerId, string[]> = {
  none: [],
  "4m": ["ladder_fuels_4m"],
  "8m": ["ladder_fuels_8m"],
};

const ALL_LADDER_LAYERS = ["ladder_fuels_4m", "ladder_fuels_8m"];

const ELEVATION_DIFFERENCE_CONTOUR_LAYERS = {
  minus: "elevation_difference_contour_minus",
  plus: "elevation_difference_contour_plus",
  minusFill: "elevation_difference_contour_minus_fill",
  plusFill: "elevation_difference_contour_plus_fill",
};

export function setBaseLayer(map: MapLibreMap, layerId: BaseLayerId): void {
  if (layerId === "basic") {
    Object.keys(HIGH_RES_LAYERS).forEach((id) => {
      map.setLayoutProperty(id, "visibility", "none");
    });
    return;
  }

  Object.keys(HIGH_RES_LAYERS).forEach((id) => {
    map.setLayoutProperty(id, "visibility", id === layerId ? "visible" : "none");
  });
}

export function setBaseLayerTransparency(map: MapLibreMap, sliderValue: number): void {
  const opacity = 1 - clamp(sliderValue, 0, 1);
  map.setPaintProperty("contrast", "background-opacity", opacity);
}

export function setContourVisibility(map: MapLibreMap, visible: boolean): void {
  const visibility = visible ? "visible" : "none";
  ELEVATION_CONTOUR_LAYERS.forEach((layerId) => {
    map.setLayoutProperty(layerId, "visibility", visibility);
  });
}

export function setLadderLayer(map: MapLibreMap, layerId: LadderLayerId): void {
  const visibleLayers = new Set(LADDER_LAYER_VISIBILITY[layerId]);
  ALL_LADDER_LAYERS.forEach((layer) => {
    map.setLayoutProperty(layer, "visibility", visibleLayers.has(layer) ? "visible" : "none");
  });
}

export function setElevationDifferenceContours(
  map: MapLibreMap,
  options: { showContours: boolean; showFill: boolean },
): void {
  const contourVisibility = options.showContours ? "visible" : "none";
  const fillVisibility = options.showContours && options.showFill ? "visible" : "none";
  map.setLayoutProperty(ELEVATION_DIFFERENCE_CONTOUR_LAYERS.minus, "visibility", contourVisibility);
  map.setLayoutProperty(ELEVATION_DIFFERENCE_CONTOUR_LAYERS.plus, "visibility", contourVisibility);
  map.setLayoutProperty(ELEVATION_DIFFERENCE_CONTOUR_LAYERS.minusFill, "visibility", fillVisibility);
  map.setLayoutProperty(ELEVATION_DIFFERENCE_CONTOUR_LAYERS.plusFill, "visibility", fillVisibility);
}

export function getAvailableHighResLayers(zoom: number): Record<string, boolean> {
  return Object.entries(HIGH_RES_LAYERS).reduce<Record<string, boolean>>(
    (availability, [layerId, minZoom]) => {
      availability[layerId] = zoom >= minZoom;
      return availability;
    },
    {},
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
