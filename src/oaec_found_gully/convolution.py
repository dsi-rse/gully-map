"""
GPU-accelerated image convolution and analysis tools for digital elevation models (DEMs).

This library provides efficient functions to generate oriented
convolution kernels, apply convolutions on large images using GPUs
(via CuPy and Numba), and perform operations tailored for terrain
feature extraction from DEM data. Principal features include:

- Kernel generators for disk, line, and half-disk structures, useful for detecting
  shapes and linear features.
- Fast, boundary-reflecting 2D convolution implemented with Numba CUDA.
- Utilities for patching holes in DEMs by nearest-neighbor imputation.
- Cumulative feature extraction through minimum filtering across angle stacks.
- Pixel-wise sinusoidal fitting to directional convolution responses for robust
  orientation or anisotropy analysis.

These tools enable scalable, high-performance processing of geospatial
raster data, especially for tasks involving multi-angular feature
detection in terrain analysis pipelines.
"""

from collections.abc import Callable
from typing import Tuple

import cupy as cp
import numba as nb
import numba.cuda
import numpy as np
import scipy.ndimage


def point_in_disk(
    radius: float = 50, linewidth: float = 1, antialias_scale: float = 10
) -> np.ndarray:
    """
    Generate a convolution kernel for a dot symmetrically placed within a disk.
    The kernel is designed to reduce absolute elevation to local changes within 50 pixels.

    Parameters:
        radius (float): Radius of the disk in pixels (default: 50).
        linewidth (float): Width of the line in pixels (default: 1).
        antialias_scale (float): Scale factor used for anti-aliasing.

    Returns:
        np.ndarray: 2D array kernel.
    """
    # compute size of high-resolution "big" grid for anti-aliasing
    width = 2 * radius + 1
    bigx, bigy = np.meshgrid(
        np.arange(antialias_scale * width), np.arange(antialias_scale * width)
    )
    x = bigx / antialias_scale - radius - 0.5
    y = bigy / antialias_scale - radius - 0.5

    # build the shape in large scale
    disk = x**2 + y**2 <= radius**2
    minidisk = x**2 + y**2 <= linewidth**2

    # downsample, build the output, and return
    small_disk = np.sum(
        np.sum(disk.reshape((width, antialias_scale, width, antialias_scale)), axis=-1),
        axis=-2,
    )
    small_minidisk = np.sum(
        np.sum(
            minidisk.reshape((width, antialias_scale, width, antialias_scale)), axis=-1
        ),
        axis=-2,
    )
    small_disk[small_minidisk > 0] = 0
    small_disk = -small_disk / np.sum(small_disk)
    small_disk[small_minidisk > 0] = 1 / np.sum(small_minidisk > 0)
    return small_disk


def antialiased_kernel(make_shape: Callable, radius: int, antialias_scale: float):
    """
    Constructs an anti-aliased kernel from a high-resolution grid using the provided shape generator.

    Parameters:
        make_shape (Callable): Function that takes (x, y) coordinate arrays and returns a high-resolution 2D kernel.
        radius (int): Defines the radius of the kernel in pixels (output kernel will be (2*radius+1) x (2*radius+1)).
        antialias_scale (float): Factor to upsample the grid for anti-aliasing before downsampling.

    Returns:
        np.ndarray: The resulting kernel as a 2D NumPy array, anti-aliased to the desired size.
    """
    width = 2 * radius + 1

    # compute size of high-resolution "big" grid for anti-aliasing
    bigx, bigy = np.meshgrid(
        np.arange(antialias_scale * width), np.arange(antialias_scale * width)
    )
    x = bigx / antialias_scale - (width // 2) - 0.5
    y = bigy / antialias_scale - (width // 2) - 0.5

    # build big kernel using provided function
    big = make_shape(x, y)

    # downsample and return
    return np.sum(
        np.sum(big.reshape((width, antialias_scale, width, antialias_scale)), axis=-1),
        axis=-2,
    )


def line_in_disk(
    angle: float,
    *,
    linelength: float = 15,
    radius: float = 50,
    linewidth: float = 1,
    antialias_scale: float = 10
) -> np.ndarray:
    """
    Generate a convolution kernel for a line at a given angle within a disk, with a given line length and width.
    The kernel is designed to enhance linear features in the direction of `angle`.

    Parameters:
        angle (float): Angle in degrees.
        linelength (float): The decay scale of the center line in pixels (default: 15).
        radius (float): Radius of the disk in pixels (default: 50).
        linewidth (float): Width of the line in pixels (default: 1).
        antialias_scale (float): Scale factor used for anti-aliasing.

    Returns:
        np.ndarray: 2D array kernel.
    """

    def make_shape(x, y):
        disk = x**2 + y**2 <= radius**2
        minidisk = np.exp(-(x**2 + y**2) / 2 / linelength**2) / np.sqrt(
            2 * np.pi * linelength**2
        )
        line = (
            np.abs(x * np.sin(-angle * np.pi / 180) - y * np.cos(angle * np.pi / 180))
            < linewidth
        )
        centerline = minidisk * (disk & line)
        return -(disk / np.sum(disk)) + (centerline / np.sum(centerline))

    return antialiased_kernel(make_shape, radius, antialias_scale)


def half_disk(
    angle: float,
    radius: float = 50,
    linelength: float = 15,
    antialias_scale: float = 10,
) -> np.ndarray:
    """
    Generate a convolution kernel for a half-disk at a given angle.
    The kernel is designed to be a veto against one-sided embankments, usually
    along roads, rather than two-sided gullies.

    Parameters:
        angle (float): Angle in degrees.
        radius (float): Radius of the disk in pixels (default: 50).
        linelength (float): The decay scale of the center line in pixels (default: 15).
        antialias_scale (float): Scale factor used for anti-aliasing.

    Returns:
        np.ndarray: 2D array kernel.
    """

    def make_shape(x, y):
        disk = np.exp(-(x**2 + y**2) / 2 / linelength**2) / np.sqrt(
            2 * np.pi * linelength**2
        )
        line = x * np.sin(-angle * np.pi / 180) - y * np.cos(angle * np.pi / 180) < 0
        positive = disk * line
        negative = disk * ~line
        return positive / np.sum(positive) - negative / np.sum(negative)

    return antialiased_kernel(make_shape, radius, antialias_scale)


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
    # look up the nearest non-missing neighbor for each missing pixel
    indices = scipy.ndimage.distance_transform_edt(
        missing, return_distances=False, return_indices=True
    )
    # return the value of that neighbor
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
    # move arrays to GPU
    image = cp.asarray(image, dtype=np.float32)
    kernel = cp.asarray(kernel, dtype=np.float32)
    output = cp.zeros_like(image)

    assert image.shape[0] > kernel.shape[0]
    assert image.shape[1] > kernel.shape[1]

    # compile or reuse Numba CUDA kernel for a hard-coded size
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

    # run CUDA kernel for convolution
    convolve2d._kernels[key][blockspergrid, threadsperblock](image, kernel, output)

    # block until finished so that only one image is in VRAM at a time (limited memory)
    return output.get()


convolve2d._kernels = {}  # compiled function cache for the convolve2d function


@nb.jit
def argmin_across_angles(convolutions: Tuple[16, np.ndarray]) -> np.ndarray:
    """
    Returns the index of the input array with the minimum value at each pixel.

    For each pixel position, finds which of the 16 input 2D arrays has the smallest
    value and returns a new 2D array of indices in the range 0..15.

    Args:
        convolutions (Tuple[16, np.ndarray]): Sequence of sixteen 2D numpy arrays
            (all the same shape), e.g., responses at 16 angles.

    Returns:
        np.ndarray: 2D array of int64, same shape as input arrays, where each entry
        is the index (0..15) of the array with the minimum value at that pixel.
    """
    assert len(convolutions) == 16

    output = np.zeros(convolutions[0].shape, dtype=np.int64)

    # for each pixel
    for i in range(convolutions[0].shape[0]):
        for j in range(convolutions[0].shape[1]):
            # find which array in the convolutions has the minimum value at this pixel
            min_value = np.inf
            min_k = 0
            for k in range(16):
                if convolutions[k][i, j] < min_value:
                    min_value = convolutions[k][i, j]
                    min_k = k
            output[i, j] = min_k

    return output


@nb.jit
def accumulate_at_argmin(
    argmin_result: np.ndarray,
    convolutions_disk: np.ndarray,
    index: int,
    output: np.ndarray,
):
    """
    Copies values from convolutions_disk to output where argmin_result equals index.

    For each pixel, if the value in argmin_result is equal to the given index,
    copies the corresponding value from convolutions_disk into output.

    Args:
        argmin_result (np.ndarray): 2D int64 array, contains indices from `argmin_across_angles`.
        convolutions_disk (np.ndarray): 2D float array of values to conditionally copy.
        index (int): Index to match in argmin_result.
        output (np.ndarray): 2D float array (same shape) modified in-place.
    """
    # for each pixel
    for i in range(argmin_result.shape[0]):
        for j in range(argmin_result.shape[1]):
            # save this convolutions_disk's pixel if we're considering that index
            if argmin_result[i, j] == index:
                output[i, j] = convolutions_disk[i, j]


@nb.jit
def sinusoidal(
    convolutions: Tuple[16, np.ndarray],
) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Fit a sinusoidal function (with constant, sine, and cosine terms) to the responses from
    convolving an image with exactly 16 uniformly spaced values from 0 up to but not including π.

    Parameters:
        Convolutions (List[np.ndarray]): List of response 16 images, ordered by angle.

    Returns:
        Tuple[np.ndarray, np.ndarray, np.ndarray]: Arrays of the fitted constant (A),
            sine (B), and cosine (C) terms per pixel.
    """
    assert len(convolutions) == 16

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
            y0 = convolutions[0][i, j]  # f(0)
            y1 = convolutions[1][i, j]  # f(π / 16)
            y2 = convolutions[2][i, j]  # f(π / 8)
            y3 = convolutions[3][i, j]  # f(3π / 16)
            y4 = convolutions[4][i, j]  # f(π / 4)
            y5 = convolutions[5][i, j]  # f(5π / 16)
            y6 = convolutions[6][i, j]  # f(3π / 8)
            y7 = convolutions[7][i, j]  # f(7π / 16)
            y8 = convolutions[8][i, j]  # f(π / 2)
            y9 = convolutions[9][i, j]  # f(9π / 16)
            y10 = convolutions[10][i, j]  # f(5π / 8)
            y11 = convolutions[11][i, j]  # f(11π / 16)
            y12 = convolutions[12][i, j]  # f(3π / 4)
            y13 = convolutions[13][i, j]  # f(13π / 16)
            y14 = convolutions[14][i, j]  # f(7π / 8)
            y15 = convolutions[15][i, j]  # f(15π / 16)

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
