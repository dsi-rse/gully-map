/**
 * MapLibre source helpers for managing draw overlays.
 */
import type { Feature, FeatureCollection, LineString, Point } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

type Coordinate = [number, number];

/**
 * Update both the polyline and point sources used to render draw overlays.
 * @param map MapLibre instance hosting the sources.
 * @param coordinates Current draw coordinates.
 */
export function updateDrawSources(map: MapLibreMap, coordinates: Coordinate[]): void {
  const lineSource = getGeoJSONSource(map, "draw-line");
  if (lineSource) {
    const lineFeature: Feature<LineString> = {
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: (coordinates.length >= 2 ? coordinates : []) as LineString["coordinates"],
      },
      properties: {},
    };
    lineSource.setData(lineFeature);
  }

  const pointSource = getGeoJSONSource(map, "draw-point");
  if (pointSource) {
    const emptyCollection: FeatureCollection<Point> = {
      type: "FeatureCollection",
      features: [],
    };
    pointSource.setData(emptyCollection);
  }
}

/**
 * Highlight a point on the map by setting the relevant GeoJSON source.
 * @param map MapLibre instance.
 * @param coordinate Coordinate to highlight, or null to clear the highlight.
 */
export function highlightDrawPoint(
  map: MapLibreMap,
  coordinate: Coordinate | null,
): void {
  const source = getGeoJSONSource(map, "draw-point");
  if (!source) {
    return;
  }

  const featureCollection: FeatureCollection<Point> =
    coordinate === null
      ? { type: "FeatureCollection", features: [] }
      : {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "Point",
                coordinates: coordinate as Point["coordinates"],
              },
              properties: {},
            },
          ],
        };

  source.setData(featureCollection);
}

/**
 * Helper for safely retrieving a GeoJSON source by id.
 * @param map MapLibre instance.
 * @param sourceId Source identifier.
 * @returns The GeoJSON source or null when unavailable.
 */
function getGeoJSONSource(map: MapLibreMap, sourceId: string): GeoJSONSource | null {
  const source = map.getSource(sourceId);
  if (source && typeof (source as GeoJSONSource).setData === "function") {
    return source as GeoJSONSource;
  }
  return null;
}
