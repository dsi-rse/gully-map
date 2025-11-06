/**
 * Helpers for calculating elevation measurements along user-drawn paths.
 */
import { getDistance } from "geolib";

import {
  getTile,
  MAX_TILES_PER_QUERY,
  pixelIndex,
  tileIndex,
  TILE_CHECK_DELAY_MS,
  type ElevationTile,
} from "./elevationTiles";
import type { ElevationPlotManager } from "./elevationPlots";

type Coordinate = [number, number];

export interface LineMeasurementOptions {
  plotManager: ElevationPlotManager;
}

/**
 * Build a controller that samples elevation tiles for a polyline and updates plots.
 * @param options Dependencies required to update the plot visuals.
 * @returns An object exposing an updateLine method used during drawing interactions.
 */
export function createLineMeasurementController(
  options: LineMeasurementOptions,
): { updateLine: (coordinates: Coordinate[], isFinal: boolean) => void } {
  let activeMeasurementToken = 0;

  /**
   * Consume a new set of coordinates to refresh the plots.
   * @param coordinates Coordinates representing the drawn path.
   * @param isFinal When true, waits for all tiles before finalising the plots.
   */
  function updateLine(coordinates: Coordinate[], isFinal: boolean): void {
    const measurementToken = ++activeMeasurementToken;

    if (coordinates.length === 0) {
      return;
    }

    const tileIds = new Set(
      coordinates.map(([lng, lat]) => tileIndex(lng, lat).join(":")),
    );

    if (tileIds.size > MAX_TILES_PER_QUERY) {
      options.plotManager.setLineTooLong(true);
      return;
    }

    options.plotManager.setLineTooLong(false);

    const distances = cumulativeDistances(coordinates);
    const tiles = coordinates.map(([lng, lat]) => getTile(...tileIndex(lng, lat)));
    const pixelPositions = coordinates.map(([lng, lat]) => pixelIndex(lng, lat));

    if (isFinal) {
      void watchUntilReady(measurementToken, tiles, distances, pixelPositions);
    } else {
      draw(measurementToken, distances, tiles, pixelPositions);
    }
  }

  /**
   * Periodically resample tiles until both years finish loading, keeping the plots responsive.
   * @param measurementToken Token identifying the active draw sequence.
   * @param tiles Elevation tiles covering the measurement path.
   * @param distances Cumulative distances for the polyline.
   * @param pixelPositions Pixel offsets within each tile.
   */
  async function watchUntilReady(
    measurementToken: number,
    tiles: ElevationTile[],
    distances: number[],
    pixelPositions: Array<[number, number]>,
  ): Promise<void> {
    while (true) {
      draw(measurementToken, distances, tiles, pixelPositions);
      if (measurementToken !== activeMeasurementToken) {
        break;
      }

      if (!tiles.some((tile) => tile.waiting())) {
        break;
      }
      await delay(TILE_CHECK_DELAY_MS);
      if (measurementToken !== activeMeasurementToken) {
        break;
      }
    }
  }

  /**
   * Sample the supplied tiles and forward data to the elevation plot manager.
   * @param measurementToken Token identifying the active draw sequence.
   * @param distances Distances for the current polyline.
   * @param tiles Cached elevation tiles.
   * @param pixelPositions Pixel indexes paired to each coordinate.
   */
  function draw(
    measurementToken: number,
    distances: number[],
    tiles: ElevationTile[],
    pixelPositions: Array<[number, number]>,
  ): void {
    if (measurementToken !== activeMeasurementToken) {
      return;
    }

    const values2013 = tiles.map((tile, index) =>
      tile.value2013(...pixelPositions[index]),
    );
    const values2022 = tiles.map((tile, index) =>
      tile.value2022(...pixelPositions[index]),
    );
    options.plotManager.update(distances, values2013, values2022);
  }

  return { updateLine };
}

/**
 * Generate cumulative distances along the supplied coordinates.
 * @param coordinates Path coordinates.
 * @returns An array where each item is the cumulative distance from the start.
 */
function cumulativeDistances(coordinates: Coordinate[]): number[] {
  let cumulative = 0;
  let previous: { longitude: number; latitude: number } | null = null;
  const results: number[] = [];

  for (const [lng, lat] of coordinates) {
    const current = { longitude: lng, latitude: lat };
    if (previous) {
      cumulative += getDistance(previous, current, 0.01);
    }
    results.push(cumulative);
    previous = current;
  }

  return results;
}

/**
 * Promise-based helper for delaying execution.
 * @param ms Number of milliseconds to wait.
 * @returns A promise that resolves after the specified delay.
 */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
