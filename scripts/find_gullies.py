import os
import math
import pathlib

import numpy as np
import cupy as cp
import numba as nb
import numba.cuda
import rasterio.warp
import PIL.Image


FEET_PER_METER = 3.28084


def disk(radius):
    radius = int(np.ceil(radius))
    width = 2 * radius + 1
    bigx, bigy = np.meshgrid(np.arange(10 * width), np.arange(10 * width))
    x = bigx / 10 - radius - 0.5
    y = bigy / 10 - radius - 0.5
    disk = x**2 + y**2 <= radius**2
    small_disk = np.sum(np.sum(disk.reshape((width, 10, width, 10)), axis=-1), axis=-2)
    return small_disk / np.sum(small_disk)


def line_in_disk(angle, *, linelength=15, radius=50, linewidth=1):
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


def convolve2d(image, kernel):
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


SIN_PI_8 = np.sin(np.pi / 8)
COS_PI_8 = np.cos(np.pi / 8)
SQRT1_2 = np.sqrt(1 / 2)
INV16 = 1 / 16
INV8 = 1 / 8


@nb.jit(parallel=True)
def sinusoidal(convolutions):
    A = np.empty(convolutions[0].shape, dtype=np.float32)
    B = np.empty(convolutions[0].shape, dtype=np.float32)
    C = np.empty(convolutions[0].shape, dtype=np.float32)

    for i in nb.prange(convolutions[0].shape[0]):
        for j in nb.prange(convolutions[0].shape[1]):
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
        A[i] = INV16 * a

        # Sine projection:
        # sin(k*pi/8) over k=0..15 is:
        # [0, s, m, c, 1, c, m, s, 0, -s, -m, -c, -1, -c, -m, -s]
        t_s = (y1 + y7) - (y9 + y15)  # weights with ±sin(pi/8)
        t_m = (y2 + y6) - (y10 + y14)  # weights with ±sqrt(1/2)
        t_c = (y3 + y5) - (y11 + y13)  # weights with ±cos(pi/8)
        t_1 = y4 - y12  # weights with ±1
        S_sum = (SIN_PI_8 * t_s) + (SQRT1_2 * t_m) + (COS_PI_8 * t_c) + t_1
        B[i] = INV8 * S_sum

        # Cosine projection:
        # cos(k*pi/8) over k=0..15 is:
        # [1, c, m, s, 0, -s, -m, -c, -1, -c, -m, -s, 0,  s,  m,  c]
        u_1 = y0 - y8  # weights with ±1
        u_c = (y1 + y15) - (y7 + y9)  # weights with ±cos(pi/8)
        u_m = (y2 + y14) - (y6 + y10)  # weights with ±sqrt(1/2)
        u_s = (y3 + y13) - (y5 + y11)  # weights with ±sin(pi/8)
        C_sum = u_1 + (COS_PI_8 * u_c) + (SQRT1_2 * u_m) + (SIN_PI_8 * u_s)
        C[i] = INV8 * C_sum

    return A, B, C


def write_geotiff(array, arrayname, name, crs, transform):
    with rasterio.open(
        DIRECTORY / "derived" / arrayname / f"{name}-{arrayname}.tif",
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        crs=crs,
        transform=transform,
    ) as file:
        file.write(array, 1)


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

    print("read 2013 elevation to get a mask")
    with rasterio.open(
        DIRECTORY / "bare-earth-hydroflattened-2013" / f"{name}_HYDROFLATTENED_BARE_EARTH.tif"
    ) as file:
        tmp_original = file.read(1)
        tmp_mask = tmp_original != -9999.0
        tmp_shrunk_mask = convolve2d(tmp_mask, disk(55 * FEET_PER_METER / 2))

        mask = np.empty(elevation.shape, dtype=np.float32)
        rasterio.warp.reproject(
            source=tmp_shrunk_mask,
            destination=mask,
            src_transform=file.transform,
            src_crs=file.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=rasterio.warp.Resampling.bilinear,
        )
        mask = 1 - mask < 1e-5

        del tmp_original
        del tmp_mask
        del tmp_shrunk_mask

    angles = np.arange(0, 180, 11.25)
    kernels5 = [line_in_disk(angle, linelength=5) for angle in angles]
    kernels15 = [line_in_disk(angle, linelength=15) for angle in angles]

    convolutions15 = [None] * len(angles)
    for index, (angle, kernel) in enumerate(zip(angles, kernels15)):
        print(f"{index:02d} convolve2d for linelength=15 {angle=}")
        convolutions15[index] = convolve2d(elevation, kernel)

    print("computing min15 and max15")
    min15 = np.full(elevation.shape, np.inf, dtype=np.float32)
    max15 = np.full(elevation.shape, -np.inf, dtype=np.float32)
    for convolution in convolutions15:
        np.minimum(min15, convolution, out=min15)
        np.maximum(max15, convolution, out=max15)

    print("writing min15 and max15")
    min15[~mask] = np.nan
    write_geotiff(min15, "min15", name, crs, transform)

    print("writing for-hand-labeling PNG")
    MIN = -10
    min15[~mask] = 0
    for_hand_labeling = (np.maximum(MIN, np.minimum(0, min15)) - MIN) / (0 - MIN)
    PIL.Image.fromarray((255 * for_hand_labeling).astype(np.uint8)).save(
        DIRECTORY / "for-hand-labeling" / f"{name}.png"
    )

    del min15

    max15[~mask] = np.nan
    write_geotiff(max15, "max15", name, crs, transform)
    del max15

    print("computing low15, highlow15, and angle15")
    A, B, C = sinusoidal(convolutions15)
    del convolutions15
    hypot = np.sqrt(B**2 + C**2)
    low15 = A - hypot
    highlow15 = (A + hypot) - low15
    angle15 = ((3/4)*np.pi - (1/2)*np.arctan2(C, B)) * (180 / np.pi) % 360
    del hypot

    print("writing low15, highlow15, and angle15")
    low15[~mask] = np.nan
    write_geotiff(low15, "low15", name, crs, transform)
    del low15

    highlow15[~mask] = np.nan
    write_geotiff(highlow15, "highlow15", name, crs, transform)
    del highlow15

    angle15[~mask] = np.nan
    write_geotiff(angle15, "angle15", name, crs, transform)
    del angle15

    convolutions5 = [None] * len(angles)
    for index, (angle, kernel) in enumerate(zip(angles, kernels5)):
        print(f"{index:02d} convolve2d for linelength=5 {angle=}")
        convolutions5[index] = convolve2d(elevation, kernel)

    print("computing min5 and max5")
    min5 = np.full(elevation.shape, np.inf, dtype=np.float32)
    max5 = np.full(elevation.shape, -np.inf, dtype=np.float32)
    for convolution in convolutions5:
        np.minimum(min5, convolution, out=min5)
        np.maximum(max5, convolution, out=max5)

    print("writing min5 and max5")
    min5[~mask] = np.nan
    write_geotiff(min5, "min5", name, crs, transform)
    del min5

    max5[~mask] = np.nan
    write_geotiff(max5, "max5", name, crs, transform)
    del max5

    print("computing low5 and highlow5")
    A, B, C = sinusoidal(convolutions5)
    del convolutions5
    hypot = np.sqrt(B**2 + C**2)
    low5 = A - hypot
    highlow5 = (A + hypot) - low5
    del hypot

    print("writing low5 and highlow5")
    low5[~mask] = np.nan
    write_geotiff(low5, "low5", name, crs, transform)
    del low5

    highlow5[~mask] = np.nan
    write_geotiff(highlow5, "highlow5", name, crs, transform)
    del highlow5

    print(f"END {name}")
