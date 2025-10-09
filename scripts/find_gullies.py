"""
Geospatial DEM (Digital Elevation Model) Feature Extraction and Analysis

This module processes hydro-flattened bare-earth elevation data (GeoTIFF DEM files) to compute
multi-scale, multi-directional terrain features such as minima, maxima, and directional statistics.
It applies custom directional convolution kernels to the DEM using GPU acceleration, synthesizes
sinusoidal fits across angles, fills missing data, and writes derived products as GeoTIFFs and PNGs
for further analysis and hand-labeling.

Main components:
- Construction of line-shaped convolution kernels at multiple angles and scales.
- 2D convolution on GPU with boundary reflection using Numba and CuPy.
- Patch-filling of missing elevation values using nearest neighbors.
- Computation of minimum, maximum, and fitted sinusoidal (Fourier-like) statistics over orientations.
- Saving of processed outputs and derived statistics as georeferenced raster products.

This script is intended to be run as part of a SLURM array job, processing one DEM tile per task,
and expects a specific directory structure and file-naming convention.
"""

import os
import math
import pathlib
from typing import Any

import numpy as np
import cupy as cp
import numba as nb
import numba.cuda
import rasterio.warp
import scipy.ndimage
import PIL.Image
from affine import Affine


FEET_PER_METER = 3.28084


def line_in_disk(
    angle: float, *, linelength: float = 15, radius: float = 50, linewidth: float = 1
) -> np.ndarray:
    """
    Generate a convolution kernel for a line at a given angle within a disk, with a given line length and width.
    The kernel is designed to enhance linear features in the direction of `angle`.

    Parameters:
        angle (float): Angle in degrees.
        linelength (float): The decay scale of the center line (default: 15).
        radius (float): Radius of the disk (default: 50).
        linewidth (float): Width of the line (default: 1).

    Returns:
        np.ndarray: 2D array kernel.
    """
    width = 2 * radius + 1
    bigx, bigy = np.meshgrid(np.arange(10 * width), np.arange(10 * width))
    x = bigx / 10 - radius - 0.5
    y = bigy / 10 - radius - 0.5
    disk = x**2 + y**2 <= radius**2
    minidisk = np.exp(-(x**2 + y**2) / 2 / linelength**2) / np.sqrt(
        2 * np.pi * linelength**2
    )
    line = (
        np.abs(x * np.sin(-angle * np.pi / 180) - y * np.cos(angle * np.pi / 180))
        < linewidth
    )
    centerline = minidisk * (disk & line)
    big = -(disk / np.sum(disk)) + (centerline / np.sum(centerline))
    small = np.sum(np.sum(big.reshape((width, 10, width, 10)), axis=-1), axis=-2)
    return small


def half_disk(angle: float, radius: float = 50, linelength: float = 15) -> np.ndarray:
    """
    Generate a convolution kernel for a half-disk at a given angle.
    The kernel is designed to be a veto against one-sided embankments, usually
    along roads, rather than two-sided gullies.

    Parameters:
        angle (float): Angle in degrees.
        radius (float): Radius of the disk (default: 50).
        linelength (float): The decay scale of the center line (default: 15).

    Returns:
        np.ndarray: 2D array kernel.
    """
    width = 2 * radius + 1
    bigx, bigy = np.meshgrid(np.arange(10 * width), np.arange(10 * width))
    x = bigx / 10 - radius - 0.5
    y = bigy / 10 - radius - 0.5
    disk = np.exp(-(x**2 + y**2) / 2 / linelength**2) / np.sqrt(
        2 * np.pi * linelength**2
    )
    line = x * np.sin(-angle * np.pi / 180) - y * np.cos(angle * np.pi / 180) < 0
    positive = disk * line
    negative = disk * ~line
    big = positive / np.sum(positive) - negative / np.sum(negative)
    small = np.sum(np.sum(big.reshape((width, 10, width, 10)), axis=-1), axis=-2)
    return small


def patch_with_nearest(elevation: np.ndarray) -> np.ndarray:
    """
    Patch missing values in a DEM (represented by extremely large/small values)
    by replacing them with the value of the nearest valid neighbor.

    Parameters:
        elevation (np.ndarray): 2D array of elevations with holes.

    Returns:
        np.ndarray: Elevation array with missing values filled.
    """
    missing = abs(elevation) > 1e30
    indices = scipy.ndimage.distance_transform_edt(
        missing, return_distances=False, return_indices=True
    )
    return elevation[tuple(indices)]


def convolve2d(image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """
    Perform 2D convolution using GPU acceleration (CuPy/Numba).
    The implementation reflects boundaries.

    Parameters:
        image (np.ndarray): 2D input array.
        kernel (np.ndarray): 2D kernel array.

    Returns:
        np.ndarray: 2D output array after convolution.
    """
    image = cp.asarray(image, dtype=np.float32)
    kernel = cp.asarray(kernel, dtype=np.float32)
    output = cp.zeros_like(image)

    key = (image.shape, kernel.shape)
    if key not in convolve2d._kernels:
        imageI, imageJ = image.shape
        kernelI, kernelJ = kernel.shape

        @nb.cuda.jit
        def fcn(image, kernel, output):
            imi, imj = nb.cuda.grid(2)
            if imi >= imageI or imj >= imageJ:
                return

            halfI = kernelI // 2
            halfJ = kernelJ // 2

            accumulate = 0
            for ki in range(kernelI):
                for kj in range(kernelJ):
                    # boundary conditions that reflect
                    i = abs(imi + ki - halfI)
                    j = abs(imj + kj - halfJ)
                    i = i if i < imageI else 2 * imageI - i - 1
                    j = j if j < imageJ else 2 * imageJ - j - 1
                    accumulate += image[i, j] * kernel[ki, kj]

            output[imi, imj] = accumulate

        convolve2d._kernels[key] = fcn

    assert nb.cuda.get_current_device().MAX_THREADS_PER_BLOCK >= 1024
    threadsperblock = (32, 32)
    blockspergrid_i = int(np.ceil(image.shape[0] / threadsperblock[0]))
    blockspergrid_j = int(np.ceil(image.shape[1] / threadsperblock[1]))
    blockspergrid = (blockspergrid_i, blockspergrid_j)

    convolve2d._kernels[key][blockspergrid, threadsperblock](image, kernel, output)

    # if this were not a blocking call, the GPU's VRAM would be overloaded
    out = output.get()
    del image
    del kernel
    del output
    return out


convolve2d._kernels = {}


@nb.jit
def minimum_disk(
    convolutions15: list[np.ndarray],
    convolutions_disk: np.ndarray,
    index: int,
    output: np.ndarray,
) -> np.ndarray:
    """
    Fills an array of the convolutions_disk with the same angle as the minimum
    convolutions15, pixel by pixel.

    This function has to be applied cumulatively, since we can't fit all of the
    convolutions15 and all of the convolutions_disks in memory at once.

    Parameters:
        convolutions15 (list[np.ndarray]): List of length-15 line convolutions, ordered by angle.
        convolutions_disk (np.ndarray): Current half-disk convolution (for cumulative application).
        index (int): Current index (for cumulative application).
        output (np.ndarray): Array of results.

    Returns:
        None
    """
    for i in range(convolutions15[0].shape[0]):
        for j in range(convolutions15[0].shape[1]):
            min_15 = np.inf
            min_k = 0
            for k in range(16):
                if convolutions15[k][i, j] < min_15:
                    min_15 = convolutions15[k][i, j]
                    min_k = k
            if min_k == index:
                output[i, j] = convolutions_disk[i, j]


@nb.jit
def sinusoidal(
    convolutions: list[np.ndarray],
) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Fit a sinusoidal function (with constant, sine, and cosine terms) to the responses from
    convolving an image with multiple directional kernels.

    Parameters:
        convolutions (list[np.ndarray]): List of response images, ordered by angle.

    Returns:
        Tuple[np.ndarray, np.ndarray, np.ndarray]: Arrays of the fitted constant (A),
            sine (B), and cosine (C) terms per pixel.
    """
    SIN_PI_8 = np.sin(np.pi / 8)
    COS_PI_8 = np.cos(np.pi / 8)
    SQRT1_2 = np.sqrt(1 / 2)
    INV16 = 1 / 16
    INV8 = 1 / 8

    A = np.empty(convolutions[0].shape, dtype=np.float32)
    B = np.empty(convolutions[0].shape, dtype=np.float32)
    C = np.empty(convolutions[0].shape, dtype=np.float32)

    for i in range(convolutions[0].shape[0]):
        for j in range(convolutions[0].shape[1]):
            y0 = convolutions[0][i, j]
            y1 = convolutions[1][i, j]
            y2 = convolutions[2][i, j]
            y3 = convolutions[3][i, j]
            y4 = convolutions[4][i, j]
            y5 = convolutions[5][i, j]
            y6 = convolutions[6][i, j]
            y7 = convolutions[7][i, j]
            y8 = convolutions[8][i, j]
            y9 = convolutions[9][i, j]
            y10 = convolutions[10][i, j]
            y11 = convolutions[11][i, j]
            y12 = convolutions[12][i, j]
            y13 = convolutions[13][i, j]
            y14 = convolutions[14][i, j]
            y15 = convolutions[15][i, j]

            # Constant term is the mean
            a = y0 + y1 + y2 + y3 + y4 + y5 + y6 + y7
            a += y8 + y9 + y10 + y11 + y12 + y13 + y14 + y15
            A[i, j] = INV16 * a

            # Sine projection:
            # sin(k*pi/8) over k=0..15 is:
            # [0, s, m, c, 1, c, m, s, 0, -s, -m, -c, -1, -c, -m, -s]
            t_s = (y1 + y7) - (y9 + y15)  # weights with ±sin(pi/8)
            t_m = (y2 + y6) - (y10 + y14)  # weights with ±sqrt(1/2)
            t_c = (y3 + y5) - (y11 + y13)  # weights with ±cos(pi/8)
            t_1 = y4 - y12  # weights with ±1
            S_sum = (SIN_PI_8 * t_s) + (SQRT1_2 * t_m) + (COS_PI_8 * t_c) + t_1
            B[i, j] = INV8 * S_sum

            # Cosine projection:
            # cos(k*pi/8) over k=0..15 is:
            # [1, c, m, s, 0, -s, -m, -c, -1, -c, -m, -s, 0,  s,  m,  c]
            u_1 = y0 - y8  # weights with ±1
            u_c = (y1 + y15) - (y7 + y9)  # weights with ±cos(pi/8)
            u_m = (y2 + y14) - (y6 + y10)  # weights with ±sqrt(1/2)
            u_s = (y3 + y13) - (y5 + y11)  # weights with ±sin(pi/8)
            C_sum = u_1 + (COS_PI_8 * u_c) + (SQRT1_2 * u_m) + (SIN_PI_8 * u_s)
            C[i, j] = INV8 * C_sum

    return A, B, C


def logistic(x: float | np.ndarray) -> float | np.ndarray:
    "Logistic function: 1/(1 + exp(-x))"
    return 1 / (1 + np.exp(-x))


if __name__ == "__main__":
    DIRECTORY = pathlib.Path("/net/projects2/spun-hyper/oaec-found-gully/")
    TASK_ID = int(os.environ["SLURM_ARRAY_TASK_ID"])

    filenames = sorted((DIRECTORY / "bare-earth-hydroflattened-2022").glob("*.tif"))
    filename = filenames[TASK_ID]
    assert filename.name.endswith("_HYDROFLATTENED_BARE_EARTH.tif")
    name = filename.name[:-30]

    print(f"BEGIN {name}")

    print("read 2022 elevation")
    with rasterio.open(filenames[TASK_ID]) as file:
        elevation = file.read(1)
        transform = file.transform
        crs = file.crs

    elevation = patch_with_nearest(elevation)

    print("read 2013 elevation to get a mask")
    with rasterio.open(
        DIRECTORY
        / "bare-earth-hydroflattened-2013"
        / f"{name}_HYDROFLATTENED_BARE_EARTH.tif"
    ) as file:
        tmp_original = file.read(1)
        tmp_mask = (tmp_original != -9999.0).astype(np.float32)

        mask = np.empty(elevation.shape, dtype=np.float32)
        rasterio.warp.reproject(
            source=tmp_mask,
            destination=mask,
            src_transform=file.transform,
            src_crs=file.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=rasterio.warp.Resampling.bilinear,
        )
        mask = mask > 0.5

        del tmp_original
        del tmp_mask

    angles = np.arange(0, 180, 11.25)
    kernels5 = [line_in_disk(angle, linelength=5) for angle in angles]
    kernels15 = [line_in_disk(angle, linelength=15) for angle in angles]
    # rotated slightly so that only half of the horizontal are included at angle=0
    # so convolution with half_disk(angle) == -1 * convolution with half_disk(angle + 180)
    kernels_disk = [half_disk(angle + 1e-6) for angle in angles]

    convolutions15 = [None] * len(angles)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels15)):
        print(f"{index:02d} convolve2d for linelength=15 {angle=}")
        convolutions15[index] = convolve2d(elevation, kernel)

    mindisk = np.zeros_like(elevation)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels_disk)):
        print(f"{index:02d} convolve2d for disk {angle=}")
        convolutions_disk = convolve2d(elevation, kernel)
        minimum_disk(convolutions15, convolutions_disk, index, mindisk)

    print("computing min15")
    min15 = np.full(elevation.shape, np.inf, dtype=np.float32)
    for convolution in convolutions15:
        np.minimum(min15, convolution, out=min15)

    print("computing low15, highlow15, and angle15")
    A, B, C = sinusoidal(convolutions15)
    del convolutions15
    # if we ever want the angles, this is how to compute them:
    #     angle15 = ((3 / 4) * np.pi - (1 / 2) * np.arctan2(C, B)) * (180 / np.pi)
    hypot = np.sqrt(B**2 + C**2)
    del B, C
    low15 = A - hypot
    high15 = A + hypot
    del A, hypot

    convolutions5 = [None] * len(angles)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels5)):
        print(f"{index:02d} convolve2d for linelength=5 {angle=}")
        convolutions5[index] = convolve2d(elevation, kernel)

    print("computing min5")
    min5 = np.full(elevation.shape, np.inf, dtype=np.float32)
    for convolution in convolutions5:
        np.minimum(min5, convolution, out=min5)

    print("computing low5 and highlow5")
    A, B, C = sinusoidal(convolutions5)
    del convolutions5
    hypot = np.sqrt(B**2 + C**2)
    del B, C
    low5 = A - hypot
    high5 = A + hypot
    del A, hypot

    print("computing gully detector linear combination")
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

    print("writing gully detection")
    os.makedirs(DIRECTORY / "gully-pass1", exist_ok=True)
    with rasterio.open(
        DIRECTORY / "gully-pass1" / f"{name}-pass1.tif",
        "w",
        driver="GTiff",
        height=gully.shape[0],
        width=gully.shape[1],
        count=1,
        dtype=gully.dtype,
        crs=crs,
        transform=transform,
    ) as file:
        file.write(gully, 1)

    print("scaling down and convolving gully image")
    kernels_small = [line_in_disk(angle, radius=25, linelength=10) for angle in angles]
    mask_small = scipy.ndimage.zoom(mask, 1 / 2, order=0)
    gully_small = scipy.ndimage.zoom(gully_original, 1 / 2)
    gully_convolved = np.zeros_like(gully_small)
    for index, (angle, kernel) in enumerate(zip(angles.tolist(), kernels_small)):
        print(f"{index:02d} convolve2d for radius=25 linelength=10 {angle=}")
        np.maximum(
            gully_convolved, convolve2d(gully_small, kernel), out=gully_convolved
        )
    gully_convolved[~mask_small] = np.nan

    print("writing small, convolved gully detection")
    os.makedirs(DIRECTORY / "gully-pass2", exist_ok=True)
    with rasterio.open(
        DIRECTORY / "gully-pass2" / f"{name}-pass2.tif",
        "w",
        driver="GTiff",
        height=gully_convolved.shape[0],
        width=gully_convolved.shape[1],
        count=1,
        dtype=gully_convolved.dtype,
        crs=crs,
        transform=transform * Affine.scale(2),
    ) as file:
        file.write(gully_convolved, 1)

    print("writing connected objects")
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
            driver="GTiff",
            height=connected.shape[0],
            width=connected.shape[1],
            count=1,
            dtype=connected.dtype,
            crs=crs,
            transform=transform * Affine.scale(2),
        ) as file:
            file.write(connected, 1)

    print(f"END {name}")
