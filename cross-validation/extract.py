"""Stage 1: reduce the derived metric rasters to a compact fitting cache.

Reads ~66 GiB of float32 GeoTIFFs plus the hand-labeled PNGs and writes ~2.6
GiB of masked 1-D columns to cache/.  Replicates cell 4 of
notebooks/fit-to-hand-labeled-data.ipynb exactly, including dtype.

Once this succeeds, ~/Downloads/COPYOVER can be deleted: the cache is
self-sufficient and 25x smaller.

Usage:  python extract.py
"""

import json
import sys

import numpy as np
import PIL.Image
import rasterio
from rasterio.windows import Window

import config

PIL.Image.MAX_IMAGE_PIXELS = None  # I know my images are large; they're not DoS attacks...


def raster_path(metric, watershed):
    return config.DERIVED / metric / f"{watershed}-{metric}.tif"


def png_path(watershed, kind):
    return config.HAND_LABELED / f"{watershed}-{kind}.png"


def last_row_readable(path):
    """True if the raster's final row can be read.

    rsync --partial leaves an interrupted file under its FINAL name, so mere
    existence does not mean the transfer finished.  These rasters are
    uncompressed, so a truncated file loses its last rows and GDAL raises
    RasterioIOError when asked for them.  (File size is not a usable check:
    there is a ~0.01% strip-table overhead on top of width*height*4.)
    """
    try:
        with rasterio.open(path) as file:
            file.read(1, window=Window(0, file.height - 1, file.width, 1))
    except Exception:
        return False
    return True


def unready_inputs():
    """(missing, truncated) -- inputs that are not yet safe to read."""
    missing, truncated = [], []
    for watershed in config.WATERSHEDS:
        for kind in ("mask", "gully"):
            if not png_path(watershed, kind).exists():
                missing.append(png_path(watershed, kind))
        for metric in config.METRICS:
            path = raster_path(metric, watershed)
            if not path.exists():
                missing.append(path)
            elif not last_row_readable(path):
                truncated.append(path)
    return missing, truncated


def read_png_channel(path):
    """Read channel 1 of a hand-labeled PNG, with the notebook's guards.

    These PNGs are mode "LA", so channel 1 is ALPHA, not green.  The notebook
    wrote `np.asarray(file)[:, :, 1]`, which is the same thing for LA and is
    what produced Table 2.  Asserting the mode pins that meaning, so a future
    conversion to RGB cannot silently change which channel is read.
    """
    with PIL.Image.open(path) as file:
        assert file.mode == "LA", f"{path.name}: expected mode LA, got {file.mode}"
        channel = np.asarray(file.getchannel(1))
    assert channel.min() == 0, f"{path.name}: channel 1 min is {channel.min()}, not 0"
    assert channel.max() == 255, f"{path.name}: channel 1 max is {channel.max()}, not 255"
    return channel


def extract_watershed(watershed):
    """Return (X, y, n_before_nan_and) for one watershed."""
    mask = read_png_channel(png_path(watershed, "mask")) < 128
    gully = read_png_channel(png_path(watershed, "gully")) > 128
    assert gully.shape == mask.shape, (
        f"{watershed}: gully {gully.shape} != mask {mask.shape}"
    )
    n_before = int(mask.sum())

    # One raster is held at a time; the masked 1-D vector is kept and the
    # full raster freed immediately.  Holding all 6 at once would be 12.1 GiB
    # on Lower Dry Creek; this way the peak is ~3-4 GiB.
    vectors = {}
    nan_reference = None
    for metric in config.METRICS:
        with rasterio.open(raster_path(metric, watershed)) as file:
            data = file.read(1)
        assert data.shape == mask.shape, (
            f"{watershed}/{metric}: raster {data.shape} != mask {mask.shape}"
        )

        is_nan = np.isnan(data)
        if metric == "min15":
            # min15 comes first: it sets the NaN reference and the truth cut.
            nan_reference = is_nan
            mask &= ~nan_reference
            # NaN compares False, so NaN pixels become not-gully.
            gully &= data < config.SHARPEN
        else:
            if not np.array_equal(is_nan, nan_reference):
                raise AssertionError(
                    f"{watershed}/{metric}: NaN pattern differs from min15 in "
                    f"{int((is_nan ^ nan_reference).sum())} pixels.  The original "
                    "fit's progressive mask update assumed every metric shares "
                    "one NaN pattern; that assumption is violated here, so this "
                    "cache would not reproduce Table 2."
                )
            del is_nan

        vectors[metric] = data[mask]
        del data

    del nan_reference

    X = config.build_features(vectors)
    y = gully[mask]
    assert X.dtype == np.float32, f"expected float32 features, got {X.dtype}"
    assert len(X) == len(y)
    return X, y, n_before


def main():
    missing, truncated = unready_inputs()
    if missing or truncated:
        total = len(config.WATERSHEDS) * (len(config.METRICS) + 2)
        for label, paths in (("missing", missing), ("truncated", truncated)):
            if not paths:
                continue
            print(f"ERROR: {len(paths)} of {total} input files are {label}:",
                  file=sys.stderr)
            for path in paths[:12]:
                print(f"  {path}", file=sys.stderr)
            if len(paths) > 12:
                print(f"  ... and {len(paths) - 12} more", file=sys.stderr)
        print("\nThe COPYOVER download is probably still in progress.",
              file=sys.stderr)
        return 1

    config.CACHE.mkdir(exist_ok=True)

    X_parts, y_parts, group_parts, manifest = [], [], [], []
    for index, watershed in enumerate(config.WATERSHEDS):
        print(f"[{index + 1}/{len(config.WATERSHEDS)}] {watershed} ...",
              end=" ", flush=True)
        X, y, n_before = extract_watershed(watershed)
        n, n_positive = len(y), int(y.sum())
        print(f"{n / 1e6:.3f} M rows, {n_positive / 1e6:.3f} M positive "
              f"({100 * n_positive / n:.2f}%)"
              + ("" if n == n_before else
                 f"  [mask lost {n_before - n} px to NaN]"), flush=True)

        X_parts.append(X)
        y_parts.append(y)
        group_parts.append(np.full(n, index, dtype=np.int8))
        manifest.append({
            "watershed": watershed,
            "index": index,
            "rows": n,
            "rows_before_nan_and": n_before,
            "positive": n_positive,
        })

    X = np.concatenate(X_parts)
    y = np.concatenate(y_parts)
    groups = np.concatenate(group_parts)
    del X_parts, y_parts, group_parts

    print(f"\nTOTAL {len(y) / 1e6:.3f} M rows, {int(y.sum()) / 1e6:.3f} M positive "
          f"({100 * y.mean():.2f}%)")
    print(f"      X is {X.nbytes / 2**30:.2f} GiB {X.dtype} {X.shape}")

    np.save(config.CACHE / "X.npy", X)
    np.save(config.CACHE / "y.npy", y)
    np.save(config.CACHE / "groups.npy", groups)
    (config.CACHE / "manifest.json").write_text(json.dumps({
        "watersheds": manifest,
        "metrics": config.METRICS,
        "features": config.FEATURES,
        "sharpen": config.SHARPEN,
        "total_rows": len(y),
        "total_positive": int(y.sum()),
    }, indent=2))

    print(f"\nWrote {config.CACHE}/")
    print("~/Downloads/COPYOVER can now be deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
