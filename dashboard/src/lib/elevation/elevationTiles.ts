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

export function tileIndex(lng: number, lat: number): [number, number] {
  const tileX = Math.floor(((lng + 180) / 360) * Math.pow(2, TILE_ZOOM));
  const tileY = Math.floor(
    ((1 - Math.log(Math.tan(toRadians(lat)) + 1 / Math.cos(toRadians(lat))) / Math.PI) / 2) *
      Math.pow(2, TILE_ZOOM),
  );
  return [tileX, tileY];
}

export function pixelIndex(lng: number, lat: number): [number, number] {
  const scale = TILE_SIZE * Math.pow(2, TILE_ZOOM);
  const worldX = (lng + 180) / 360;
  const sinLat = Math.sin(toRadians(lat));
  const worldY = 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI);
  const pixelX = Math.round(worldX * scale);
  const pixelY = Math.round(worldY * scale);
  const x = mod(pixelX, TILE_SIZE);
  const y = mod(pixelY, TILE_SIZE);
  return [x, y];
}

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

  function valueFromView(view: DataView | null, x: number, y: number): number | null {
    if (!view || x < 0 || y < 0 || x >= TILE_SIZE || y >= TILE_SIZE) {
      return null;
    }

    const index = y * TILE_SIZE + x;
    const value = view.getFloat32(4 * index, true);
    return value < 3e38 ? value : null;
  }

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

function decodeToView(data: ArrayBuffer | Uint8Array): DataView | null {
  const image = upng.decode(data);
  const rgba = upng.toRGBA8(image)[0];
  return new DataView(rgba, 0, rgba.length);
}

function createKey(tileX: number, tileY: number): TileKey {
  return `${tileX}:${tileY}`;
}

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function mod(n: number, m: number): number {
  return ((n % m) + m) % m;
}
