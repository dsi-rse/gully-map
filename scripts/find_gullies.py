import os
import math
import pathlib

import numpy as np
import cupy as cp
import numba as nb
import numba.cuda
import rasterio
import PIL


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

    kernels15 = {
        angle: line_in_disk(angle, linelength=15)
        for angle in np.arange(0, 180, 11.25)
    }

    min15 = np.full(elevation.shape, np.inf, dtype=np.float32)
    for angle, kernel in kernels15.items():
        print(f"convolve2d for {angle=} linelength=15")
        convolution = convolve2d(elevation, kernel)
        np.minimum(min15, convolution, out=min15)
        del convolution

    for_hand_labeling = (np.maximum(-10, np.minimum(0, min15)) - -10) / (0 - -10)
    PIL.Image.fromarray((255 * for_hand_labeling).astype(np.uint8)).save(
        DIRECTORY / "for-hand-labeling" / f"{name}.png"
    )

    print(f"END {name}")
