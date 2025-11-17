/**
 * Convenience helpers for toggling visibility of MapLibre basemap and overlay layers.
 */
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

/**
 * Activate a basemap layer while hiding the others.
 * @param map MapLibre instance.
 * @param layerId Basemap identifier to show.
 */
export function setBaseLayer(map: MapLibreMap, layerId: BaseLayerId): void {
  if (layerId == "hillshade_greyscale" || layerId == "hillshade_color_enhanced") {
    map.setPaintProperty("gully_detection_pass3", "line-color", "#0051ff");
  }
  else {
    map.setPaintProperty("gully_detection_pass3", "line-color", "#9ebdff");
  }

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

/**
 * Adjust the opacity of the contrast base tiles to simulate hiding the basemap.
 * @param map MapLibre instance.
 * @param sliderValue Range slider value between 0 and 1.
 */
export function setBaseLayerTransparency(map: MapLibreMap, sliderValue: number): void {
  const opacity = 1 - clamp(sliderValue, 0, 1);
  map.setPaintProperty("contrast", "background-opacity", opacity);
}

/**
 * Toggle visibility for the hillshade contour overlays.
 * @param map MapLibre instance.
 * @param visible Whether the contour layers should be visible.
 */
export function setContourVisibility(map: MapLibreMap, visible: boolean): void {
  const visibility = visible ? "visible" : "none";
  ELEVATION_CONTOUR_LAYERS.forEach((layerId) => {
    map.setLayoutProperty(layerId, "visibility", visibility);
  });
}

/**
 * Switch between ladder fuel ratios or disable them entirely.
 * @param map MapLibre instance.
 * @param layerId Requested ladder fuel overlay.
 */
export function setLadderLayer(map: MapLibreMap, layerId: LadderLayerId): void {
  const visibleLayers = new Set(LADDER_LAYER_VISIBILITY[layerId]);
  ALL_LADDER_LAYERS.forEach((layer) => {
    map.setLayoutProperty(layer, "visibility", visibleLayers.has(layer) ? "visible" : "none");
  });
}

/**
 * Control the family of elevation-difference contour layers.
 * @param map MapLibre instance.
 * @param options Visibility flags for contour lines and fill polygons.
 */
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

/**
 * Determine which high-resolution basemap layers are available at a given zoom.
 * @param zoom Current map zoom level.
 * @returns Object mapping layer ids to boolean availability.
 */
export function getAvailableHighResLayers(zoom: number): Record<string, boolean> {
  return Object.entries(HIGH_RES_LAYERS).reduce<Record<string, boolean>>(
    (availability, [layerId, minZoom]) => {
      availability[layerId] = zoom >= minZoom;
      return availability;
    },
    {},
  );
}

/**
 * Clamp a numeric value to the provided interval.
 * @param value Value to clamp.
 * @param min Lower bound.
 * @param max Upper bound.
 * @returns Clamped value.
 */
function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
