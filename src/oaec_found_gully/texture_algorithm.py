import math
import threading
import queue

import numpy as np
import rasterio

NUM_THREADS = 10

def nextprod(a: list[int], x: int) -> int:
    """
    Next integer greater than or equal to `x` that can be written as ``\\prod k_i^{a_i}`` for integers ``a_1``, ``a_2``, etc.

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


def window_loop(shape, chunk, axis=0, reverse=False, overlap=0, offset=0):
    """
    Construct a frame to extract chunks of data from gdal
    (and to insert them properly to a numpy matrix)
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


def texture_shading(dem_array: np.ndarray, alpha: float = 0.5):
    ysize, xsize = dem_array.shape
    chunk_y, chunk_x = 244, 225
    chunk_slice_x = ysize, chunk_x
    chunk_slice_y = chunk_y, xsize

    Ny = nextprod([2, 3, 5, 7], ysize)
    Nx = nextprod([2, 3, 5, 7], xsize)
    fy = np.fft.rfftfreq(Ny)[:, np.newaxis]
    fx = np.fft.rfftfreq(Nx)[np.newaxis, :]
    Hy, Hx = (fy**2) ** alpha, (fx**2) ** alpha

    tasks = queue.Queue()
    for axis in [0, 1]:
        if axis == 0:
            chunk = chunk_x
        elif axis == 1:
            chunk = chunk_y

        for window in window_loop(shape=(xsize, ysize), chunk=chunk, axis=axis):
            tasks.put((axis, window))

    for _ in range(NUM_THREADS):
        tasks.put(None)

    out_array = np.zeros_like(dem_array)

    def worker():
        while True:
            task = tasks.get()
            if task is None:
                break

            axis, (mx_view_in, gdal_take, mx_view_out, gdal_put) = task

            if axis == 0:
                N, H = Ny, Hy
            elif axis == 1:
                N, H = Nx, Hx

            jstart, istart, jsize, isize = gdal_take
            mx_z = dem_array[istart : istart + isize, jstart : jstart + jsize]

            r = np.fft.rfft(mx_z, N, axis=axis) * H
            r = np.fft.irfft(r, axis=axis)

            # return the same size as input
            out = r[: mx_z.shape[0], : mx_z.shape[1]]

            jstart, istart, jsize, isize = gdal_put
            out_array[istart : istart + isize, jstart : jstart + jsize] += out[mx_view_out]

    threads = [threading.Thread(target=worker) for _ in range(NUM_THREADS)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    return out_array


if __name__ == "__main__":
    with rasterio.open("Dutch Bill Creek_HYDROFLATTENED_BARE_EARTH.tif") as dem_file:
        dem_array = dem_file.read(1)
        dem_profile = dem_file.profile

    out_array = texture_shading(dem_array, 0.5)

    with rasterio.open("testy.tif", "w", **dem_profile) as output:
        output.write(out_array, 1)
