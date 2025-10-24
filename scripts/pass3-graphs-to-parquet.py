"""
Module for extracting and converting gully network paths from raster 'graph' files.
The script loads each watershed's pass3-graph.tif, traces linear and junction paths
using the 8-connected adjacency in the raster, simplifies coordinates, and exports
the result into a Parquet file including information about endpoints and path geometry
in lon/lat.

Dependencies:
    - numpy
    - rasterio
    - pyproj
    - pyarrow
    - simplification (Visvalingam-Whyatt algorithm)
"""

import pathlib
from collections import Counter
from typing import Any

import numpy as np
import rasterio.transform
import pyproj
import pyarrow as pa
import pyarrow.parquet as pq
from simplification.cutil import simplify_coords_vw

DIRECTORY = pathlib.Path("~/Downloads/gully-pass3").expanduser()

# bitmasks for 8-connected neighborhood directions
connected_NW = np.uint8(0b00000001)
connected_N = np.uint8(0b00000010)
connected_NE = np.uint8(0b00000100)
connected_W = np.uint8(0b00001000)
connected_E = np.uint8(0b00010000)
connected_SW = np.uint8(0b00100000)
connected_S = np.uint8(0b01000000)
connected_SE = np.uint8(0b10000000)


def possible_steps(
    i1: int, j1: int, i2: int, j2: int, graph: np.ndarray
) -> list[(int, int)]:
    """
    Get all possible steps from position (i2, j2), except for (i1, j1), where adjacency is indicated by nonzero bits in graph.

    Args:
        i1, j1: Previous position.
        i2, j2: Current position.
        graph: 2D uint8 array with bitmasks for connectivity.

    Returns:
        List of neighbor (i, j) tuples that are connected and not (i1, j1).
    """
    out: list[(int, int)] = []
    if graph[i2, j2] & connected_NW:
        i3, j3 = i2 - 1, j2 - 1
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    if graph[i2, j2] & connected_N:
        i3, j3 = i2 - 1, j2
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    if graph[i2, j2] & connected_NE:
        i3, j3 = i2 - 1, j2 + 1
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    if graph[i2, j2] & connected_W:
        i3, j3 = i2, j2 - 1
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    if graph[i2, j2] & connected_E:
        i3, j3 = i2, j2 + 1
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    if graph[i2, j2] & connected_SW:
        i3, j3 = i2 + 1, j2 - 1
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    if graph[i2, j2] & connected_S:
        i3, j3 = i2 + 1, j2
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    if graph[i2, j2] & connected_SE:
        i3, j3 = i2 + 1, j2 + 1
        if (i3, j3) != (i1, j1):
            out.append((i3, j3))
    return out


def only_step(pair1: (int, int), pair2: (int, int), graph: np.ndarray) -> (int, int):
    """
    Return the only possible next step from pair2 given pair1, assuming there is only one.

    Used for traversing a linear (degree-2) segment.

    Args:
        pair1: Previous (i, j).
        pair2: Current (i, j).
        graph: 2D uint8 array of connectivity.

    Returns:
        (i, j) of the only neighbor (besides pair1), or an empty tuple if none.

    Raises:
        `Exception("dead end")` if there are no new nodes to step to.
    """
    i1, j1 = pair1
    i2, j2 = pair2
    if graph[i2, j2] & connected_NW:
        i3, j3 = i2 - 1, j2 - 1
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    if graph[i2, j2] & connected_N:
        i3, j3 = i2 - 1, j2
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    if graph[i2, j2] & connected_NE:
        i3, j3 = i2 - 1, j2 + 1
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    if graph[i2, j2] & connected_W:
        i3, j3 = i2, j2 - 1
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    if graph[i2, j2] & connected_E:
        i3, j3 = i2, j2 + 1
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    if graph[i2, j2] & connected_SW:
        i3, j3 = i2 + 1, j2 - 1
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    if graph[i2, j2] & connected_S:
        i3, j3 = i2 + 1, j2
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    if graph[i2, j2] & connected_SE:
        i3, j3 = i2 + 1, j2 + 1
        if (i3, j3) != (i1, j1):
            return (i3, j3)
    raise Exception("dead end")


def is_linear(pair: (int, int), num_connections: np.ndarray) -> bool:
    """
    Check if the site has exactly two neighbors (linear segment).

    Args:
        pair: (i, j) tuple for index.
        num_connections: 2D array with connection count per cell.

    Returns:
        True if degree == 2.
    """
    i, j = pair
    return num_connections[i, j] == 2


def find_paths(
    graph: np.ndarray, num_connections: np.ndarray
) -> list[list[(int, int)]]:
    """
    Trace out paths from endpoints or junctions, traversing along linear chains.
    Starts from all locations with degree 1 (tips) or >=3 (junctions).

    Args:
        graph: 2D uint8 array with bitmasks for connection.
        num_connections: 2D int array with number of neighbor connections for each pixel.

    Returns:
        List of paths, where each path is a list of (i, j) tuples.
    """
    # find "seeds": all junction and endpoint locations
    path_seeds = np.concatenate(
        [
            np.dstack(np.nonzero(num_connections == 1))[0],  # endpoints
            np.dstack(np.nonzero(num_connections >= 3))[0],  # junctions
        ],
        axis=0,
    )

    paths = []
    for i1, j1 in path_seeds:
        seen = set()
        for i2, j2 in possible_steps(i1, j1, i1, j1, graph):
            for i3, j3 in possible_steps(i1, j1, i2, j2, graph):
                if (i3, j3) not in seen:
                    seen.add((i3, j3))
                    path = [(i1, j1), (i2, j2), (i3, j3)]
                    # continue walking until the path reaches a non-linear point
                    while is_linear(path[-1], num_connections):
                        path.append(only_step(path[-2], path[-1], graph))
                    paths.append(path)

    return paths


if __name__ == "__main__":
    # columns of the output Parquet file
    watersheds = []
    endpoints_lon = []
    endpoints_lat = []
    endpoints_junction_count = []
    paths_lon = []
    paths_lat = []
    paths_start_endpoint_id = []
    paths_stop_endpoint_id = []

    for filename in sorted(DIRECTORY.glob("*-pass3-graph.tif")):
        watershed = filename.name[:-16]
        print(f"converting: {watershed}")

        with rasterio.open(filename) as file:
            graph = file.read(1)
            index_to_crs = file.transform
            crs_to_lonlat = pyproj.Transformer.from_crs(
                file.crs, "EPSG:4326", always_xy=True
            )

        def index_to_lonlat(i, j):
            """
            Convert raster (i, j) index to (longitude, latitude) using CRS info.
            """
            return crs_to_lonlat.transform(*rasterio.transform.xy(index_to_crs, i, j))

        # compute the degree of each node (number of connected neighbors)
        num_connections = np.unpackbits(graph).reshape(graph.shape + (8,)).sum(axis=-1)
        paths = find_paths(graph, num_connections)

        # ensure only longest path through a midpoint is kept, to avoid duplicates
        matches_by_midpoint = {}
        for path in paths:
            for pair in path:
                if is_linear(pair, num_connections):
                    if pair not in matches_by_midpoint:
                        matches_by_midpoint[pair] = []
                    matches_by_midpoint[pair].append(path)

        longest_by_midpoint = {}
        for midpoint, matches in matches_by_midpoint.items():
            longest_by_midpoint[midpoint] = sorted(matches, key=len)[-1]

        unique_paths = sorted(
            set(tuple(match) for match in longest_by_midpoint.values()),
            key=len,
            reverse=True,
        )

        # simplify path geometry using Visvalingam-Whyatt algorithm (threshold=10 units)
        simplified_paths = [simplify_coords_vw(path, 10.0) for path in unique_paths]

        # assign endpoint IDs for start/stop (with spatial "fuzzing" to merge near-duplicates)
        endpoints: dict[(int, int), int] = {}
        junction_count = Counter()

        def get_approximate_endpoint(
            pair: (int, int), endpoints: dict[(int, int), int]
        ) -> int:
            """
            Return endpoint id for a given (i, j) location (with fuzzy matching
            for nearby cells), allocating new id if not present.
            """
            i, j = pair
            for di, dj in [
                (0, 0),
                (0, -1),
                (0, 1),
                (-1, 0),
                (1, 0),
                (-1, -1),
                (-1, 1),
                (1, -1),
                (1, 1),
            ]:
                endpoint_id = endpoints.get((i + di, j + dj))
                if endpoint_id is not None:
                    return endpoint_id

            endpoint_id = len(endpoints)
            endpoints[(i, j)] = endpoint_id
            return endpoint_id

        simplified_paths_starts = []
        simplified_paths_stops = []
        for path in simplified_paths:
            start = get_approximate_endpoint(path[0], endpoints)
            stop = get_approximate_endpoint(path[-1], endpoints)
            simplified_paths_starts.append(start)
            simplified_paths_stops.append(stop)
            junction_count[start] += 1
            junction_count[stop] += 1

        watersheds.append(watershed)

        endpoints_lonlat = [index_to_lonlat(i, j) for i, j in endpoints.keys()]
        endpoints_lon.append([lon for lon, lat in endpoints_lonlat])
        endpoints_lat.append([lat for lon, lat in endpoints_lonlat])

        endpoints_junction_count.append(
            [junction_count[endpoint_id] for endpoint_id in endpoints.values()]
        )

        paths_lonlat = [
            [index_to_lonlat(i, j) for i, j in path] for path in simplified_paths
        ]
        paths_lon.append([[lon for lon, lat in path] for path in paths_lonlat])
        paths_lat.append([[lat for lon, lat in path] for path in paths_lonlat])

        paths_start_endpoint_id.append(simplified_paths_starts)
        paths_stop_endpoint_id.append(simplified_paths_stops)

    # Arrow arrays and write as Parquet
    watersheds = pa.array(watersheds)
    endpoints_lon = pa.array(endpoints_lon)
    endpoints_lat = pa.array(endpoints_lat)
    endpoints_junction_count = pa.array(endpoints_junction_count)
    paths_lon = pa.array(paths_lon)
    paths_lat = pa.array(paths_lat)
    paths_start_endpoint_id = pa.array(paths_start_endpoint_id)
    paths_stop_endpoint_id = pa.array(paths_stop_endpoint_id)

    print("writing output...")
    pq.write_table(
        pa.Table.from_arrays(
            [
                watersheds,
                endpoints_lon,
                endpoints_lat,
                endpoints_junction_count,
                paths_lon,
                paths_lat,
                paths_start_endpoint_id,
                paths_stop_endpoint_id,
            ],
            [
                "watersheds",
                "endpoints_lon",
                "endpoints_lat",
                "endpoints_junction_count",
                "paths_lon",
                "paths_lat",
                "paths_start_endpoint_id",
                "paths_stop_endpoint_id",
            ],
        ),
        "gully-detection-pass3-graph.parquet",
        compression="snappy",
    )

    print("done")
