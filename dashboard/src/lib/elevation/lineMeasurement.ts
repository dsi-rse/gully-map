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

export function createLineMeasurementController(
  options: LineMeasurementOptions,
): { updateLine: (coordinates: Coordinate[], isFinal: boolean) => void } {
  function updateLine(coordinates: Coordinate[], isFinal: boolean): void {
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
      void watchUntilReady(tiles, distances, pixelPositions);
    } else {
      draw(distances, tiles, pixelPositions);
    }
  }

  async function watchUntilReady(
    tiles: ElevationTile[],
    distances: number[],
    pixelPositions: Array<[number, number]>,
  ): Promise<void> {
    while (true) {
      draw(distances, tiles, pixelPositions);
      if (!tiles.some((tile) => tile.waiting())) {
        break;
      }
      await delay(TILE_CHECK_DELAY_MS);
    }
  }

  function draw(
    distances: number[],
    tiles: ElevationTile[],
    pixelPositions: Array<[number, number]>,
  ): void {
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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
