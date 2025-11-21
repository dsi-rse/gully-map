/**
 * Manages PMTiles elevation downloads, caching and conversions ready for plotting.
 */
import { PMTiles } from "pmtiles";
import upng from "upng-js";

export interface ElevationTile {
  value2013: (x: number, y: number) => number | null;
  value2022: (x: number, y: number) => number | null;
  waiting: () => boolean;
}

const TILE_SIZE = 256;
const TILE_ZOOM = 17;
const TILE_CACHE_SIZE = 100;
export const MAX_TILES_PER_QUERY = 10;
export const TILE_CHECK_DELAY_MS = 100;

const elevation2013 = new PMTiles("https://uchicago-dsi-oaec.s3.us-east-1.amazonaws.com/elevation-2013.pmtiles");
const elevation2022 = new PMTiles("https://uchicago-dsi-oaec.s3.us-east-1.amazonaws.com/elevation-2022.pmtiles");

type TileKey = string;
type TileCache = Map<TileKey, CachedElevationTile>;

const cache: TileCache = new Map();

interface CachedElevationTile extends ElevationTile {
  touch: () => void;
}

const cacheOrder: TileKey[] = [];

/**
 * Compute the PMTiles tile indices covering a longitude/latitude pair.
 * @param lng Longitude in degrees.
 * @param lat Latitude in degrees.
 * @returns [x, y] tile coordinates at the configured zoom level.
 */
export function tileIndex(lng: number, lat: number): [number, number] {
  const tileX = Math.floor(((lng + 180) / 360) * Math.pow(2, TILE_ZOOM));
  const tileY = Math.floor(
    ((1 - Math.log(Math.tan(toRadians(lat)) + 1 / Math.cos(toRadians(lat))) / Math.PI) / 2) *
      Math.pow(2, TILE_ZOOM),
  );
  return [tileX, tileY];
}

/**
 * Translate geographic coordinates into pixel offsets within a PMTiles tile.
 * @param lng Longitude in degrees.
 * @param lat Latitude in degrees.
 * @returns [x, y] pixel coordinates.
 */
export function pixelIndex(lng: number, lat: number): [number, number] {
  const scale = TILE_SIZE * Math.pow(2, TILE_ZOOM);
  const worldX = (lng + 180) / 360;
  const sinLat = Math.sin(toRadians(lat));
  const worldY = 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI);
  const pixelX = Math.floor(worldX * scale);
  const pixelY = Math.floor(worldY * scale);
  const x = mod(pixelX, TILE_SIZE);
  const y = mod(pixelY, TILE_SIZE);
  return [x, y];
}

/**
 * Retrieve a tile from cache or start an asynchronous download when missing.
 * @param tileX X index at the configured zoom.
 * @param tileY Y index at the configured zoom.
 * @returns A tile wrapper exposing sample functions plus loading state.
 */
export function getTile(tileX: number, tileY: number): ElevationTile {
  const key = createKey(tileX, tileY);

  if (cache.has(key)) {
    const cached = cache.get(key)!;
    cached.touch();
    return cached;
  }

  const tile = downloadTile(tileX, tileY);
  cache.set(key, tile);
  cacheOrder.push(key);

  if (cacheOrder.length > TILE_CACHE_SIZE) {
    const oldestKey = cacheOrder.shift();
    if (oldestKey) {
      cache.delete(oldestKey);
    }
  }

  return tile;
}

// For computing the median of neighboring pixels
const NEIGHBORS = [
  [-1, -1], [ 0, -1], [ 1, -1],
  [-1,  0], [ 0,  0], [ 1,  0],
  [-1,  1], [ 0,  1], [ 1,  1],
];
const medianWindow = new Float32Array(9);

/**
 * Download both years worth of elevation data for the supplied tile coordinates.
 * @param tileX X index for the tile.
 * @param tileY Y index for the tile.
 * @returns A cached tile wrapper that lazily exposes tile data once available.
 */
function downloadTile(tileX: number, tileY: number): CachedElevationTile {
  let view2013: DataView | null = null;
  let view2022: DataView | null = null;
  let waiting2013 = true;
  let waiting2022 = true;
  let retries2013 = 3;
  let retries2022 = 3;

  const errors2013: unknown[] = [];
  const errors2022: unknown[] = [];

  let promise2013 = elevation2013.getZxy(TILE_ZOOM, tileX, tileY);
  let promise2022 = elevation2022.getZxy(TILE_ZOOM, tileX, tileY);

  promise2013.then(
    (response) => {
      view2013 = response ? decodeToView(response.data) : null;
      waiting2013 = false;
    },
    handleError2013,
  );

  promise2022.then(
    (response) => {
      view2022 = response ? decodeToView(response.data) : null;
      waiting2022 = false;
    },
    handleError2022,
  );

  /**
   * Retry downloads for the 2013 dataset, tracking errors for diagnostics.
   * @param error Failure encountered while downloading a tile.
   */
  function handleError2013(error: unknown): void {
    errors2013.push(error);
    if (retries2013-- > 0) {
      waiting2013 = true;
      promise2013 = elevation2013.getZxy(TILE_ZOOM, tileX, tileY);
      promise2013.then(
        (response) => {
          view2013 = response ? decodeToView(response.data) : null;
          waiting2013 = false;
        },
        handleError2013,
      );
    } else {
      waiting2013 = false;
    }
  }

  /**
   * Retry downloads for the 2022 dataset, tracking errors for diagnostics.
   * @param error Failure encountered while downloading a tile.
   */
  function handleError2022(error: unknown): void {
    errors2022.push(error);
    if (retries2022-- > 0) {
      waiting2022 = true;
      promise2022 = elevation2022.getZxy(TILE_ZOOM, tileX, tileY);
      promise2022.then(
        (response) => {
          view2022 = response ? decodeToView(response.data) : null;
          waiting2022 = false;
        },
        handleError2022,
      );
    } else {
      waiting2022 = false;
    }
  }

  /**
   * Read an elevation value from the provided data view.
   * @param view Data buffer for a tile.
   * @param x Pixel x coordinate.
   * @param y Pixel y coordinate.
   * @returns The elevation scalar or null when unavailable.
   */
  function valueFromView(view: DataView | null, x: number, y: number): number | null {
    if (!view) {
      return null;
    }

    let count = 0;
    for (const [dx, dy] of NEIGHBORS) {
      const xx = x + dx;
      const yy = y + dy;
      if (0 <= xx && xx < TILE_SIZE && 0 <= yy && yy < TILE_SIZE) {
        const index = yy * TILE_SIZE + xx;
        const value = view.getFloat32(4 * index, true);
        if (value < 3e38) {
          medianWindow[count++] = value;
        }
      }
    }
    if (count === 0) {
      return null;  // No valid values
    }

    // Sort the populated part of medianWindow
    const arr = Array.from(medianWindow.subarray(0, count));
    arr.sort((a, b) => a - b);
    const mid = Math.floor(count / 2);
    return count % 2 === 1 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
  }

  /** Maintain LRU ordering when a cached tile is accessed. */
  const touch = (): void => {
    const index = cacheOrder.indexOf(createKey(tileX, tileY));
    if (index >= 0) {
      cacheOrder.splice(index, 1);
      cacheOrder.push(createKey(tileX, tileY));
    }
  };

  return {
    value2013: (x, y) => valueFromView(view2013, x, y),
    value2022: (x, y) => valueFromView(view2022, x, y),
    waiting: () => waiting2013 || waiting2022,
    touch,
  };
}

/**
 * Decode a PMTiles PNG response into a DataView for sampling.
 * @param data Raw tile data.
 * @returns A DataView exposing the elevation floats.
 */
function decodeToView(data: ArrayBuffer | Uint8Array): DataView | null {
  const image = upng.decode(data);
  const rgba = upng.toRGBA8(image)[0];
  return new DataView(rgba, 0, rgba.length);
}

/**
 * Create a string key for caching tiles.
 * @param tileX X coordinate.
 * @param tileY Y coordinate.
 * @returns Unique cache key string.
 */
function createKey(tileX: number, tileY: number): TileKey {
  return `${tileX}:${tileY}`;
}

/**
 * Convert degrees to radians.
 * @param degrees Angle in degrees.
 * @returns Angle in radians.
 */
function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/**
 * Positive modulus helper that handles negative inputs gracefully.
 * @param n Value to wrap.
 * @param m Modulus base.
 * @returns Wrapped value in the [0, m) interval.
 */
function mod(n: number, m: number): number {
  return ((n % m) + m) % m;
}
