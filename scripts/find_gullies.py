import os
import math
import pathlib

import numpy as np
import cupy as cp
import numba as nb
import numba.cuda
import rasterio
import PIL.Image


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
def best_fit(convolutions):
    A = np.empty_like(convolutions[0])
    B = np.empty_like(convolutions[0])
    C = np.empty_like(convolutions[0])

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


if __name__ == "__main__":
    DIRECTORY = pathlib.Path("/net/projects2/spun-hyper/oaec-found-gullies/")
    JOBID = int(os.environ["SLURM_ARRAY_TASK_ID"])

    filenames = sorted((DIRECTORY / "bare-earth-hydroflattened-2022").glob("*.tif"))
    filename = filenames[JOBID]
    assert filename.name.endswith("_HYDROFLATTENED_BARE_EARTH.tif")
    name = filename.name[:-30]

    print(f"BEGIN {name}")

    with rasterio.open(filenames[JOBID]) as file:
        elevation = file.read(1)
        transform = file.transform
        crs = file.crs

    angles = np.arange(0, 180, 11.25)
    kernels15 = [line_in_disk(angle, linelength=15) for angle in angles]

    convolutions15 = [None] * len(angles)
    for index, (angle, kernel) in enumerate(zip(angles, kernels15)):
        print(f"{index:02d} convolve2d for linelength=15 {angle=}")
        convolutions15[index] = convolve2d(elevation, kernel)

    min15 = np.full(elevation.shape, np.inf, dtype=np.float32)
    for convolution in convolutions15:
        np.minimum(min15, convolution, out=min15)

    print("writing for-hand-labeling PNG")
    MIN = -10
    for_hand_labeling = (np.maximum(MIN, np.minimum(0, min15)) - MIN) / (0 - MIN)
    PIL.Image.fromarray((255 * for_hand_labeling).astype(np.uint8)).save(
        DIRECTORY / "for-hand-labeling" / f"{name}.png"
    )

    print(f"END {name}")
