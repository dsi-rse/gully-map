"""
Gully Extraction Pipeline for Elevation Data Tiles

This script processes high-resolution hydroflattened bare-earth elevation raster tiles
from two different years (2013 and 2022) to detect potential gully erosion features.
Processing is performed on a per-tile basis and supports parallel array jobs, where the
tile is selected via `SLURM_ARRAY_TASK_ID`.

Major steps performed:

1. **Data Preparation:**
   - Loads target (2022) and reference (2013) elevation rasters for a specific tile.
   - Reprojects 2013 data and masks to align with the 2022 grid.
   - Patches missing elevation values.

2. **Multi-Scale Convolution Feature Extraction:**
   - Applies a range of oriented line and disk convolution kernels at two scales (5 and 15 px).
   - Combines multi-angle responses to extract statistics (e.g., min, sinusoidal fit).
   - Computes local elevation differences between years.

3. **Gully Likelihood Estimation:**
   - Produces a pixelwise gully detection score via a logistic regression linear combination
     of multi-scale convolutional features.

4. **Multi-Resolution and Post-Processing:**
   - Downsamples and smooths the gully likelihood to create a coarser probability map.
   - Identifies connected components (clusters) at several score thresholds.
   - Skeletonizes the final gully probability map to extract linear gully structures.

5. **Output:**
   - Writes rasters at each stage (elevation difference, gully probability, convolved images,
     clusters, skeleton) to output subfolders.

**Intended usage:**
    sbatch find_gullies.sh

The script is designed to run in a SLURM array job environment and expects environment
variable SLURM_ARRAY_TASK_ID to index the current raster tile.
"""

import logging
import os
import pathlib
import sys

import numpy as np
import rasterio.warp
import scipy.ndimage
from affine import Affine

from oaec_found_gully.convolution import (
    point_in_disk,
    line_in_disk,
    half_disk,
    patch_with_nearest,
    convolve2d,
    argmin_across_angles,
    accumulate_at_argmin,
    sinusoidal,
    low_high,
)
from oaec_found_gully.skeletonization import skeletonize

FEET_PER_METER = 3.28084

# write options that are common to all output files
WRITE_OPTIONS = {
    "driver": "GTiff",
    "count": 1,
    "crs": crs,
    "compress": "LZW",
    "tiled": True,
    "blockxsize": 1024,
    "blockysize": 1024,
}


def logistic(x: float | np.ndarray) -> float | np.ndarray:
    "Logistic function: 1/(1 + exp(-x))"
    return 1 / (1 + np.exp(-x))


if __name__ == "__main__":
    # task configuration; exactly one argument is required
    (DIRECTORY,) = sys.argv[1:]
    DIRECTORY = pathlib.Path(DIRECTORY)
    TASK_ID = int(os.environ["SLURM_ARRAY_TASK_ID"])

    filenames = sorted((DIRECTORY / "bare-earth-hydroflattened-2022").glob("*.tif"))
    filename = filenames[TASK_ID]
    assert filename.name.endswith("_HYDROFLATTENED_BARE_EARTH.tif")
    name = filename.name[:-30]

    # set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)

    logger.info(f"BEGIN {name}")

    logger.info("read 2022 elevation")
    with rasterio.open(filenames[TASK_ID]) as file:
        elevation2022 = file.read(1)
        transform = file.transform
        crs = file.crs

    logger.info("patch missing data in 2022 elevation")
    mask2022 = abs(elevation2022) < 1e30  # True for valid pixels
    elevation2022 = patch_with_nearest(elevation2022)

    # prepare convolution kernels
    angles = np.arange(0, 180, 11.25)
    kernels5 = [
        line_in_disk(angle, linelength=5, radius=50, linewidth=1) for angle in angles
    ]
    kernels15 = [
        line_in_disk(angle, linelength=15, radius=50, linewidth=1) for angle in angles
    ]
    # rotated slightly so that only half of the horizontal are included at angle=0
    # so convolution with half_disk(angle) == -1 * convolution with half_disk(angle + 180)
    kernels_disk = [
        half_disk(angle + 1e-6, radius=50, linelength=15) for angle in angles
    ]

    # convolutions with the 15-pixel line_in_disk kernels, one for each angle
    convolutions15 = [None] * len(angles)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels15)):
        logger.info(f"{index:02d} convolve2d for linelength=15 {angle=}")
        convolutions15[index] = convolve2d(elevation2022, kernel)

    # minimum angle index for each pixel
    argmin_result = argmin_across_angles(tuple(convolutions15))

    # convolutions with the half_disk kernels, one for each angle
    # the half_disk corresponding to the minimum convolutions15 is accumulated with a minimum of memory use
    mindisk = np.zeros_like(elevation2022)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels_disk)):
        logger.info(f"{index:02d} convolve2d for disk {angle=}")
        convolutions_disk = convolve2d(elevation2022, kernel)
        accumulate_at_argmin(argmin_result, convolutions_disk, index, mindisk)

    # strict minimum 15-pixel line_in_disk kernel
    logger.info("computing min15")
    min15 = np.full(elevation2022.shape, np.inf, dtype=np.float32)
    for convolution in convolutions15:
        np.minimum(min15, convolution, out=min15)

    # best-fit to a sinusoidal dependence on angle
    logger.info("computing low15 and highlow15")
    low15, high15 = low_high(*sinusoidal(tuple(convolutions15)))
    # if we ever want the angles, this is how to compute them:
    #     angle15 = ((3 / 4) * np.pi - (1 / 2) * np.arctan2(C, B)) * (180 / np.pi)

    del convolutions15

    # convolutions with the 5-pixel line_in_disk kernels, one for each angle
    convolutions5 = [None] * len(angles)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels5)):
        logger.info(f"{index:02d} convolve2d for linelength=5 {angle=}")
        convolutions5[index] = convolve2d(elevation2022, kernel)

    # strict minimum 5-pixel line_in_disk kernel
    logger.info("computing min5")
    min5 = np.full(elevation2022.shape, np.inf, dtype=np.float32)
    for convolution in convolutions5:
        np.minimum(min5, convolution, out=min5)

    # best-fit to a sinusoidal dependence on angle
    logger.info("computing low5 and highlow5")
    low5, high5 = low_high(*sinusoidal(tuple(convolutions5)))

    del convolutions5

    logger.info("read 2013 elevation for 9-year differences and the watershed mask")
    with rasterio.open(
        DIRECTORY
        / "bare-earth-hydroflattened-2013"
        / f"{name}_HYDROFLATTENED_BARE_EARTH.tif"
    ) as file:
        tmp_original = file.read(1)
        tmp_mask = (tmp_original != file.nodata).astype(np.float32)

        # reproject to match the 2022 grid
        elevation2013 = np.empty(elevation2022.shape, dtype=tmp_original.dtype)
        rasterio.warp.reproject(
            source=tmp_original,
            destination=elevation2013,
            src_transform=file.transform,
            src_crs=file.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=rasterio.warp.Resampling.bilinear,
            src_nodata=file.nodata,
        )
        # convert vertical elevation from feet to meters
        elevation2013 /= FEET_PER_METER

        # reproject the mask as well
        mask = np.empty(elevation2022.shape, dtype=np.float32)
        rasterio.warp.reproject(
            source=tmp_mask,
            destination=mask,
            src_transform=file.transform,
            src_crs=file.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=rasterio.warp.Resampling.bilinear,
        )
        mask = mask > 0.5  # True for valid pixels
        mask &= mask2022  # both years must be valid

        del tmp_original
        del tmp_mask

    logger.info("writing local elevation difference")
    point_kernel = point_in_disk(radius=50, linewidth=1)
    local_elevation2022 = convolve2d(elevation2022, point_kernel)
    local_elevation2013 = convolve2d(elevation2013, point_kernel)
    elevdiff = local_elevation2022 - local_elevation2013
    elevdiff[~mask] = np.nan
    os.makedirs(DIRECTORY / "gully-pass0", exist_ok=True)
    with rasterio.open(
        DIRECTORY / "gully-pass0" / f"{name}-elevdiff.tif",
        "w",
        height=elevdiff.shape[0],
        width=elevdiff.shape[1],
        dtype=elevdiff.dtype,
        transform=transform,
        **WRITE_OPTIONS,
    ) as file:
        file.write(elevdiff, 1)

    logger.info("computing gully detector linear combination")
    gully = logistic(
        -9.800051565013556
        + -3.1639324806178912 * (min15)
        + -0.7209343186388889 * (low15 - min15)
        + 1.9421691573124356 * (high15 - low15)
        + 0.19531310261020537 * (min5 - min15)
        + -0.2707981230014441 * (high5 - low5)
        + 0.6326805610644737 * (low15 * (high15 - low15))
        + -0.28814988058815305 * abs(mindisk)
    )
    gully_original = gully.copy()
    gully[~mask] = np.nan

    logger.info("writing gully detection")
    os.makedirs(DIRECTORY / "gully-pass1", exist_ok=True)
    with rasterio.open(
        DIRECTORY / "gully-pass1" / f"{name}-pass1.tif",
        "w",
        height=gully.shape[0],
        width=gully.shape[1],
        dtype=gully.dtype,
        transform=transform,
        **WRITE_OPTIONS,
    ) as file:
        file.write(gully, 1)

    logger.info("scaling down and convolving gully image")
    kernels_small = [
        line_in_disk(angle, linelength=10, radius=25, linewidth=1) for angle in angles
    ]
    mask_small = scipy.ndimage.zoom(mask, 1 / 2, order=0)
    gully_small = scipy.ndimage.zoom(gully_original, 1 / 2)
    gully_convolved = np.zeros_like(gully_small)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels_small)):
        logger.info(f"{index:02d} convolve2d for radius=25 linelength=10 {angle=}")
        np.maximum(
            gully_convolved, convolve2d(gully_small, kernel), out=gully_convolved
        )
    gully_convolved[~mask_small] = np.nan

    logger.info("writing small, convolved gully detection")
    os.makedirs(DIRECTORY / "gully-pass2", exist_ok=True)
    with rasterio.open(
        DIRECTORY / "gully-pass2" / f"{name}-pass2.tif",
        "w",
        height=gully_convolved.shape[0],
        width=gully_convolved.shape[1],
        dtype=gully_convolved.dtype,
        transform=transform * Affine.scale(2),
        **WRITE_OPTIONS,
    ) as file:
        file.write(gully_convolved, 1)

    logger.info("writing connected component clustering results")
    os.makedirs(DIRECTORY / "gully-pass3", exist_ok=True)
    all8corners = scipy.ndimage.generate_binary_structure(2, 2)
    connected1, _ = scipy.ndimage.label(gully_convolved > 0.01, all8corners)
    connected2, _ = scipy.ndimage.label(gully_convolved > 0.02, all8corners)
    connected4, _ = scipy.ndimage.label(gully_convolved > 0.04, all8corners)
    connected8, _ = scipy.ndimage.label(gully_convolved > 0.08, all8corners)
    for percent, connected in zip(
        [1, 2, 4, 8], [connected1, connected2, connected4, connected8]
    ):
        with rasterio.open(
            DIRECTORY / "gully-pass3" / f"{name}-pass3-{percent}.tif",
            "w",
            height=connected.shape[0],
            width=connected.shape[1],
            dtype=connected.dtype,
            transform=transform * Affine.scale(2),
            **WRITE_OPTIONS,
        ) as file:
            file.write(connected, 1)

    logger.info("writing skeletonized graph results")
    edges = skeletonize(gully_convolved, 0.01)  # uint8 with 0 meaning no node
    with rasterio.open(
        DIRECTORY / "gully-pass3" / f"{name}-pass3-graph.tif",
        "w",
        height=edges.shape[0],
        width=edges.shape[1],
        dtype=edges.dtype,
        transform=transform * Affine.scale(2),
        **WRITE_OPTIONS,
    ) as file:
        file.write(edges, 1)

    logger.info(f"END {name}")
