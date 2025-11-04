"""
Module for efficient tiled processing and texture shading of large digital elevation models (DEMs).

This module provides utilities for:
- Efficiently finding the smallest product of integer powers of given bases greater than or equal to an input value (`nextprod`, `nextpow`).
- Chunked/tiled processing of large 2D arrays through windowing (`window_loop`), with flexible chunk size, overlap, direction, and axis.
- Parallelized, frequency-domain texture shading of DEMs using fast Fourier transforms (`texture_shading`), for use in rendering or terrain visualization.

Dependencies:
- numpy
- rasterio
"""

import math
import threading
import queue

import numpy as np
import numba as nb
import rasterio
import numba


NUM_THREADS = 10


def nextprod(a: list[int], x: int) -> int:
    """
    Next integer greater than or equal to `x` that can be written as ``\\prod k_i^{a_i}`` for integers ``a_1``, ``a_2``, etc.

    Copied from https://github.com/zoran-cuckovic/QGIS-terrain-shading/blob/f8033c00b0173cbd555bf2d3f6a2b476292a6ec3/modules/helpers.py#L224-L260

    # Examples
    ```jldoctest
    julia> nextprod([2, 3], 105)
    108
    julia> 2^2 * 3^3
    108
    ```
    """
    k = len(a)
    v = [1] * k  # current value of each counter
    mx = [nextpow(ai, x) for ai in a]  # maximum value of each counter
    v[0] = mx[0]  # start at first case that is >= x
    p = mx[0]  # initial value of product in this case
    best = p
    icarry = 1

    while v[-1] < mx[-1]:
        if p >= x:
            best = p if p < best else best  # keep the best found yet
            carrytest = True
            while carrytest:
                p = p // v[icarry - 1]
                v[icarry - 1] = 1
                icarry += 1
                p *= a[icarry - 1]
                v[icarry - 1] *= a[icarry - 1]
                carrytest = v[icarry - 1] > mx[icarry - 1] and icarry < k
            if p < x:
                icarry = 1
        else:
            while p < x:
                p *= a[0]
                v[0] *= a[0]
    return int(mx[-1] if mx[-1] < best else best)


def nextpow(a: float, x: float) -> float:
    """
    The smallest `a^n` not less than `x`, where `n` is a non-negative integer.

    Copied from https://github.com/zoran-cuckovic/QGIS-terrain-shading/blob/f8033c00b0173cbd555bf2d3f6a2b476292a6ec3/modules/helpers.py#L199-L220

    `a` must be greater than 1, and `x` must be greater than 0.
    # Examples
    ```jldoctest
    julia> nextpow(2, 7)
    8
    julia> nextpow(2, 9)
    16
    julia> nextpow(5, 20)
    25
    julia> nextpow(4, 16)
    16
    ```
    """
    assert x > 0 and a > 1
    if x <= 1:
        return 1.0
    n = math.ceil(math.log(x, a))
    p = a ** (n - 1)
    return p if p >= x else a**n


def window_loop(
    shape: (int, int),
    chunk: (int, int),
    axis: int = 0,
    reverse: bool = False,
    overlap: int = 0,
    offset: int = 0,
):
    """
    Generator for tiling large 2D arrays into windows/chunks with optional overlap and direction.

    Copied from https://github.com/zoran-cuckovic/QGIS-terrain-shading/blob/f8033c00b0173cbd555bf2d3f6a2b476292a6ec3/modules/helpers.py#L43-L106

    This function yields index descriptors for extracting and placing tiles or chunks when processing large arrays in pieces,
    such as reading/writing with GDAL/rasterio or processing in memory with numpy.

    Args:
        shape (tuple of int): Shape of the full array as (width, height).
        chunk (tuple of int): Desired chunk size as (width, height); only one dimension used per loop, based on `axis`.
        axis (int, optional): Axis along which to chunk; 0 for rows (height), 1 for columns (width). Default is 0.
        reverse (bool, optional): If True, process in reverse order along the chosen axis. Default is False.
        overlap (int, optional): Number of overlapping pixels between neighboring chunks. Default is 0.
        offset (int, optional): Pixel offset to apply to each chunk origin (can be negative or positive). Default is 0.

    Yields:
        tuple: (in_view, gdal_take, out_view, gdal_put)
            - in_view: numpy index/slice for extracting the chunk from a larger array.
            - gdal_take: tuple for reading the chunk from disk (x_off, y_off, x_size, y_size).
            - out_view: numpy index/slice for inserting the processed chunk into the output array.
            - gdal_put: tuple for writing the chunk to disk (x_off, y_off, x_size, y_size).

    Example:
        >>> for in_view, gdal_take, out_view, gdal_put in window_loop((1024, 1024), (256, 256), axis=0, overlap=16):
        ...     # Use gdal_take to read a window from a raster file
        ...     chunk = raster.read(window=gdal_take)
        ...     # process 'chunk' here...
        ...     # Insert the result into a numpy array using out_view
        ...     out_array[out_view] = processed_chunk

    Notes:
        - For most raster formats, 'shape' should be (width, height).
        - Only one axis is chunked per call; chunk size along the other axis is ignored.
        - Overlap is applied on both sides of each chunk where possible, unless at the edges.
    """
    xsize, ysize = shape if axis == 0 else shape[::-1]

    if reverse:
        begin, step, stride = xsize, 1 + xsize // chunk, -1
    else:
        begin, step, stride = 0, 0, 1

    x, y, x_off, y_off = 0, 0, xsize, ysize
    end = 1

    while xsize > end > 0:
        step += stride
        end = min(int(chunk * step), xsize)

        if reverse:
            x, x_off = end, begin - end
        else:
            x, x_off = begin, end - begin

        # move window front or back, which means only one margin will overlap
        if (offset < 0 and x >= abs(offset)) or (offset > 0 and x <= xsize - offset):
            x += offset * int(step)

        begin = end

        ov = overlap
        ov_left = min(ov, x)  # do not spill over the border
        ov_right = min(ov, (xsize - (x + x_off)))

        x_in = x - ov_left
        x_in_off = x_off + ov_right + ov_left

        if not axis:
            gdal_take = (x_in, y, x_in_off, y_off)
        else:
            gdal_take = (y, x_in, y_off, x_in_off)

        in_view = np.s_[:, :x_in_off] if not axis else np.s_[:x_in_off, :]

        x_out = x if ov_left == ov else 0
        x_out_off = (
            x_off
            + (ov_left if ov_left < ov else 0)
            + (ov_right if ov_right < ov else 0)
        )

        if not axis:
            gdal_put = (x_out, y, x_out_off, y_off)
        else:
            gdal_put = (y, x_out, y_off, x_out_off)

        sx = slice(
            0 if ov_left < ov else ov,
            x_out_off + ov_left + (ov_right if ov_right < ov else 0),
        )

        out_view = np.s_[:, sx] if not axis else np.s_[sx, :]

        yield in_view, gdal_take, out_view, gdal_put


def texture_shading(dem_array: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """
    Applies frequency-domain texture shading to a digital elevation model (DEM) array.

    This function enhances the surface texture of a DEM using a power-law filter
    in the frequency domain, suitable for visualization or analysis. The computation is
    performed efficiently in parallel using chunked processing with FFTs.

    Args:
        dem_array (np.ndarray): 2D array containing elevation data.
        alpha (float, optional): Exponent for the frequency filter.
            Higher values increase the texture contrast. Default is 0.5.

    Returns:
        np.ndarray: 2D array of the same shape as `dem_array`, containing the
            texture-shaded DEM.

    Example:
        >>> import rasterio
        >>> from texture_module import texture_shading
        >>> with rasterio.open("input_dem.tif") as src:
        ...     dem = src.read(1)
        >>> shaded = texture_shading(dem, alpha=0.6)
    """
    ysize, xsize = dem_array.shape
    chunk_y, chunk_x = 244, 225
    chunk_slice_x = ysize, chunk_x
    chunk_slice_y = chunk_y, xsize

    Ny = nextprod([2, 3, 5, 7], ysize)
    Nx = nextprod([2, 3, 5, 7], xsize)
    fy = np.fft.rfftfreq(Ny)[:, np.newaxis]
    fx = np.fft.rfftfreq(Nx)[np.newaxis, :]
    Hy, Hx = (fy**2) ** alpha, (fx**2) ** alpha

    out_array = np.zeros_like(dem_array)

    for axis in [0, 1]:
        if axis == 0:
            chunk = chunk_x
            N, H = Ny, Hy
        elif axis == 1:
            chunk = chunk_y
            N, H = Nx, Hx

        tasks = queue.Queue()

        for window in window_loop(shape=(xsize, ysize), chunk=chunk, axis=axis):
            tasks.put(window)

        for _ in range(NUM_THREADS):
            tasks.put(None)

        def worker():
            while True:
                task = tasks.get()
                if task is None:
                    break

                mx_view_in, gdal_take, mx_view_out, gdal_put = task

                jstart, istart, jsize, isize = gdal_take
                mx_z = dem_array[istart : istart + isize, jstart : jstart + jsize]

                r = np.fft.rfft(mx_z, N, axis=axis) * H
                r = np.fft.irfft(r, axis=axis)

                # return the same size as input
                out = r[: mx_z.shape[0], : mx_z.shape[1]]

                jstart, istart, jsize, isize = gdal_put
                out_array[istart : istart + isize, jstart : jstart + jsize] += out[
                    mx_view_out
                ]

        # fork-join parallelism, all writing to the same out_array
        threads = [threading.Thread(target=worker) for _ in range(NUM_THREADS)]
        for thread in threads:
            thread.start()
        # synchronize after each axis (axes overlap, but windows within an axis don't)
        for thread in threads:
            thread.join()

    return out_array


@nb.jit(parallel=True)
def colorize_hillshade(texture: np.ndarray, hillshade: np.ndarray, clamp: float = 0.1) -> np.ndarray:
    overlaid = np.empty((4, texture.shape[0], texture.shape[1]), dtype=np.uint8)
    overlaid[3] = 255

    blue = (0 / 255, 57 / 255, 255 / 255)
    green = (0 / 255, 123 / 255, 41 / 255)
    yellow = (255 / 255, 255 / 255, 128 / 255)

    for i in nb.prange(texture.shape[0]):
        for j in nb.prange(texture.shape[1]):
            # scaled is between -1 and 1
            scaled = texture[i, j]
            scaled = -clamp if scaled < -clamp else (clamp if scaled > clamp else scaled)
            scaled /= clamp

            if scaled < 0:
                t = -scaled
                colored_0 = (1 - t) * green[0] + t * blue[0]
                colored_1 = (1 - t) * green[1] + t * blue[1]
                colored_2 = (1 - t) * green[2] + t * blue[2]
            else:
                t = scaled
                colored_0 = (1 - t) * green[0] + t * yellow[0]
                colored_1 = (1 - t) * green[1] + t * yellow[1]
                colored_2 = (1 - t) * green[2] + t * yellow[2]

            # overlay colored on top of hill
            # https://en.wikipedia.org/wiki/Blend_modes#Overlay
            hill = hillshade[i, j] / 255
            if hill < 0.5:
                overlaid[0, i, j] = (2 * hill * colored_0) * 255
                overlaid[1, i, j] = (2 * hill * colored_1) * 255
                overlaid[2, i, j] = (2 * hill * colored_2) * 255
            else:
                overlaid[0, i, j] = (1 - 2 * (1 - hill) * (1 - colored_0)) * 255
                overlaid[1, i, j] = (1 - 2 * (1 - hill) * (1 - colored_1)) * 255
                overlaid[2, i, j] = (1 - 2 * (1 - hill) * (1 - colored_2)) * 255

    return overlaid


if __name__ == "__main__":
    with rasterio.open("Lower Salmon Creek_HYDROFLATTENED_BARE_EARTH.tif") as file:
        dem_array = file.read(1)
        dem_profile = file.profile

    with rasterio.open("Lower Salmon Creek_HILLSHADE.tif") as file:
        hillshade = file.read(1)

    missing_data = abs(dem_array) > 1e30
    dem_array[missing_data] = 0

    print("making texture")
    texture = texture_shading(dem_array, 0.5)

    print("making overlaid")
    overlaid = colorize_hillshade(texture, hillshade)

    overlaid[3, missing_data] = 0

    print("writing")
    dem_profile["count"] = 4
    dem_profile["dtype"] = "uint8"
    dem_profile["nodata"] = None
    with rasterio.open("testy.tif", "w", **dem_profile) as file:
        file.write(overlaid, [1, 2, 3, 4])

    print("done")
