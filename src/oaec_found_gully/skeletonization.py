"""
Module for morphological skeletonization of binary raster images.

This module implements skeletonization using node/edge graphs and an
articulation-point preserving thinning algorithm. It uses Numba for performance.

Functions:
    add_edges:         Adds edges for newly activated nodes.
    add_node:          Adds a node and updates neighbors and edges.
    remove_node:       Removes a node and updates edges of neighbors.
    edges_from_nodes:  Builds edge array from node connectivity.
    queue_*:           Helpers for a simple ring-buffer queue.
    set_seeds:         Enumerates neighbors for region-growing.
    remove_if_not_articulation: Removes non-articulation nodes if possible.
    skeletonize_impl:  Main thinning logic.
    skeletonize:       Public function to skeletonize a binary bitmap.
"""

import numpy as np
import numba as nb

# bitmasks for 8-connected neighborhood directions
connected_NW = np.uint8(0b00000001)
connected_N = np.uint8(0b00000010)
connected_NE = np.uint8(0b00000100)
connected_W = np.uint8(0b00001000)
connected_E = np.uint8(0b00010000)
connected_SW = np.uint8(0b00100000)
connected_S = np.uint8(0b01000000)
connected_SE = np.uint8(0b10000000)


@nb.jit
def add_edges(nodes: np.ndarray, edges: np.ndarray, i: int, j: int) -> None:
    """
    Add edge mask bits to (i, j) in `edges` (in-place) based on neighbor nodes in `nodes`.

    Args:
        nodes: 2D array of bool, True for node present.
        edges: 2D array of uint8, connectivity bitmask, modified in place.
        i: Row index.
        j: Column index.
    """
    top = i == 0
    bot = i == nodes.shape[0] - 1
    left = j == 0
    right = j == nodes.shape[1] - 1

    # test all 8 neighbors, set appropriate mask if neighbor present
    if not top and not left and nodes[i - 1, j - 1]:
        edges[i, j] |= connected_NW
    if not top and nodes[i - 1, j]:
        edges[i, j] |= connected_N
    if not top and not right and nodes[i - 1, j + 1]:
        edges[i, j] |= connected_NE

    if not left and nodes[i, j - 1]:
        edges[i, j] |= connected_W
    if not right and nodes[i, j + 1]:
        edges[i, j] |= connected_E

    if not bot and not left and nodes[i + 1, j - 1]:
        edges[i, j] |= connected_SW
    if not bot and nodes[i + 1, j]:
        edges[i, j] |= connected_S
    if not bot and not right and nodes[i + 1, j + 1]:
        edges[i, j] |= connected_SE


@nb.jit
def add_node(nodes: np.ndarray, edges: np.ndarray, i: int, j: int) -> None:
    """
    Add node at (i, j) to nodes, and update edges for it and its 8 neighbors.

    Args:
        nodes: 2D bool array, will be set True at (i, j).
        edges: 2D uint8 array, connectivity bitmasks.
        i, j:  Pixel coordinates.
    """
    nodes[i, j] = True
    add_edges(nodes, edges, i, j)

    top = i == 0
    bot = i == nodes.shape[0] - 1
    left = j == 0
    right = j == nodes.shape[1] - 1

    # update neighbors' edges if they are active nodes
    if not top and not left and nodes[i - 1, j - 1]:
        add_edges(nodes, edges, i - 1, j - 1)
    if not top and nodes[i - 1, j]:
        add_edges(nodes, edges, i - 1, j)
    if not top and not right and nodes[i - 1, j + 1]:
        add_edges(nodes, edges, i - 1, j + 1)

    if not left and nodes[i, j - 1]:
        add_edges(nodes, edges, i, j - 1)
    if not right and nodes[i, j + 1]:
        add_edges(nodes, edges, i, j + 1)

    if not bot and not left and nodes[i + 1, j - 1]:
        add_edges(nodes, edges, i + 1, j - 1)
    if not bot and nodes[i + 1, j]:
        add_edges(nodes, edges, i + 1, j)
    if not bot and not right and nodes[i + 1, j + 1]:
        add_edges(nodes, edges, i + 1, j + 1)


@nb.jit
def remove_node(nodes: np.ndarray, edges: np.ndarray, i: int, j: int) -> None:
    """
    Remove node at (i, j) and mask out any edges from its neighbors to it.

    Args:
        nodes: 2D bool array, set to False at (i, j).
        edges: 2D uint8 array, with edge bits updated.
        i, j:  Coordinate to remove.
    """
    nodes[i, j] = False
    edges[i, j] = 0

    top = i == 0
    bot = i == nodes.shape[0] - 1
    left = j == 0
    right = j == nodes.shape[1] - 1

    # remove edges of neighbors that point to (i, j)
    if not top and not left and nodes[i - 1, j - 1]:
        edges[i - 1, j - 1] &= ~connected_SE
    if not top and nodes[i - 1, j]:
        edges[i - 1, j] &= ~connected_S
    if not top and not right and nodes[i - 1, j + 1]:
        edges[i - 1, j + 1] &= ~connected_SW

    if not left and nodes[i, j - 1]:
        edges[i, j - 1] &= ~connected_E
    if not right and nodes[i, j + 1]:
        edges[i, j + 1] &= ~connected_W

    if not bot and not left and nodes[i + 1, j - 1]:
        edges[i + 1, j - 1] &= ~connected_NE
    if not bot and nodes[i + 1, j]:
        edges[i + 1, j] &= ~connected_N
    if not bot and not right and nodes[i + 1, j + 1]:
        edges[i + 1, j + 1] &= ~connected_NW


@nb.jit
def edges_from_nodes(nodes: np.ndarray) -> np.ndarray:
    """
    Given a binary bitmap (2D bool), return an edges array, where bitmasks
    indicate direction of 8-connected neighbors.

    Args:
        nodes: 2D array of bool.
    Returns:
        edges: 2D array of uint8, each pixel a bitmask of directions.
    """
    edges = np.zeros(nodes.shape, dtype=np.uint8)
    for i in range(nodes.shape[0]):
        for j in range(nodes.shape[1]):
            if nodes[i, j]:
                add_edges(nodes, edges, i, j)
    return edges


@nb.jit
def queue_push(
    queue: np.ndarray, queue_start_stop: np.ndarray, value_i: int, value_j: int
) -> None:
    """
    Push (i, j) tuple onto ring buffer queue.

    Args:
        queue: (N,2) array of ints.
        queue_start_stop: 2-vector: [start, stop] index.
        value_i: Row.
        value_j: Col.
    """
    queue[queue_start_stop[1], 0] = value_i
    queue[queue_start_stop[1], 1] = value_j
    if queue_start_stop[1] + 1 < len(queue):
        queue_start_stop[1] += 1
    else:
        queue_start_stop[1] = 0


@nb.jit
def queue_pop(queue: np.ndarray, queue_start_stop: np.ndarray) -> tuple[int, int]:
    """
    Pop (i, j) from ring buffer queue.

    Args:
        queue: (N,2) array of ints.
        queue_start_stop: 2-vector [start, stop].

    Returns:
        (i, j): indices.
    """
    value_i = queue[queue_start_stop[0], 0]
    value_j = queue[queue_start_stop[0], 1]
    if queue_start_stop[0] + 1 < len(queue):
        queue_start_stop[0] += 1
    else:
        queue_start_stop[0] = 0
    return value_i, value_j


@nb.jit
def queue_is_empty(queue_start_stop: np.ndarray) -> bool:
    """
    True iff ring-buffer is empty.

    Args:
        queue_start_stop: 2-vector [start, stop]

    Returns:
        bool: True if empty.
    """
    return queue_start_stop[0] == queue_start_stop[1]


@nb.jit
def queue_clear(queue_start_stop: np.ndarray) -> None:
    """
    Clear the queue.
    """
    queue_start_stop[0] = queue_start_stop[1]


@nb.jit
def set_seeds(edges: np.ndarray, seeds: np.ndarray, i: int, j: int) -> int:
    """
    Fill `seeds` with coordinates of all 8-connected neighbors of (i,j)
    (based on edges mask at (i,j)), and return number found.

    Args:
        edges: 2D uint8 edge bitmask array.
        seeds: 8x2 int array to fill with [i, j] coords. Modified in-place.
        i, j:  Center pixel.

    Returns:
        num_seeds: int, number of connected neighbors found.
    """
    num_seeds = 0

    # test each edge bit, append neighbor to seeds list
    if edges[i, j] & connected_NW:
        seeds[num_seeds, 0] = i - 1
        seeds[num_seeds, 1] = j - 1
        num_seeds += 1
    if edges[i, j] & connected_N:
        seeds[num_seeds, 0] = i - 1
        seeds[num_seeds, 1] = j
        num_seeds += 1
    if edges[i, j] & connected_NE:
        seeds[num_seeds, 0] = i - 1
        seeds[num_seeds, 1] = j + 1
        num_seeds += 1

    if edges[i, j] & connected_W:
        seeds[num_seeds, 0] = i
        seeds[num_seeds, 1] = j - 1
        num_seeds += 1
    if edges[i, j] & connected_E:
        seeds[num_seeds, 0] = i
        seeds[num_seeds, 1] = j + 1
        num_seeds += 1

    if edges[i, j] & connected_SW:
        seeds[num_seeds, 0] = i + 1
        seeds[num_seeds, 1] = j - 1
        num_seeds += 1
    if edges[i, j] & connected_S:
        seeds[num_seeds, 0] = i + 1
        seeds[num_seeds, 1] = j
        num_seeds += 1
    if edges[i, j] & connected_SE:
        seeds[num_seeds, 0] = i + 1
        seeds[num_seeds, 1] = j + 1
        num_seeds += 1

    return num_seeds


@nb.jit
def remove_if_not_articulation(
    nodes: np.ndarray,
    edges: np.ndarray,
    seeds: np.ndarray,
    queue: np.ndarray,
    queue_start_stop: np.ndarray,
    touched: np.ndarray,
    touched_start_stop: np.ndarray,
    i: int,
    j: int,
) -> None:
    """
    Remove node (i, j) if this doesn't disconnect any of its neighbors (i.e., not an articulation point).
    Restores node if it's needed for connectivity.

    Args:
        nodes: 2D bool mask of object.
        edges: uint8 edge bitmask array.
        seeds: (8,2) for neighbors.
        queue, queue_start_stop: ring buffer (for BFS).
        touched, touched_start_stop: arrays for marking visited.
        i, j: Coordinates to test/remove.
    """
    num_seeds = set_seeds(edges, seeds, i, j)
    remove_node(nodes, edges, i, j)

    if num_seeds == 0:
        # isolated pixel had no neighbors; removing it because we don't want single-node graphs
        return False

    target_i = seeds[0, 0]
    target_j = seeds[0, 1]

    # touched marks get incremented after each seed
    touched[target_i, target_j] = touched_start_stop[0]
    touched_start_stop[1] += 1

    # test for connectivity: every other neighbor should be able to reach the target without (i,j)
    for seed_index in range(1, num_seeds):
        seed_i = seeds[seed_index, 0]
        seed_j = seeds[seed_index, 1]

        queue_clear(queue_start_stop)
        queue_push(queue, queue_start_stop, seed_i, seed_j)

        seed_is_connected = False
        while not queue_is_empty(queue_start_stop):
            current_i, current_j = queue_pop(queue, queue_start_stop)

            # if this node is touched in current or previous round, it's already connected
            if (
                touched_start_stop[0]
                <= touched[current_i, current_j]
                < touched_start_stop[1]
            ):
                seed_is_connected = True
                break  # this seed is connected to the target; we're done

            if touched[current_i, current_j] == touched_start_stop[1]:
                continue  # already visited this node for this seed

            touched[current_i, current_j] = touched_start_stop[1]

            # enqueue all connected neighbors for a breadth-first search
            if edges[current_i, current_j] & connected_NW:
                queue_push(queue, queue_start_stop, current_i - 1, current_j - 1)
            if edges[current_i, current_j] & connected_N:
                queue_push(queue, queue_start_stop, current_i - 1, current_j)
            if edges[current_i, current_j] & connected_NE:
                queue_push(queue, queue_start_stop, current_i - 1, current_j + 1)

            if edges[current_i, current_j] & connected_W:
                queue_push(queue, queue_start_stop, current_i, current_j - 1)
            if edges[current_i, current_j] & connected_E:
                queue_push(queue, queue_start_stop, current_i, current_j + 1)

            if edges[current_i, current_j] & connected_SW:
                queue_push(queue, queue_start_stop, current_i + 1, current_j - 1)
            if edges[current_i, current_j] & connected_S:
                queue_push(queue, queue_start_stop, current_i + 1, current_j)
            if edges[current_i, current_j] & connected_SE:
                queue_push(queue, queue_start_stop, current_i + 1, current_j + 1)

        touched_start_stop[1] += 1

        if not seed_is_connected:
            touched_start_stop[0] = touched_start_stop[1]
            add_node(nodes, edges, i, j)  # restore the node; we shouldn't remove it
            return

    touched_start_stop[0] = touched_start_stop[1]
    return


@nb.jit
def skeletonize_impl(
    nodes: np.ndarray,
    edges: np.ndarray,
    seeds: np.ndarray,
    queue: np.ndarray,
    queue_start_stop: np.ndarray,
    touched: np.ndarray,
    touched_start_stop: np.ndarray,
    i_index: np.ndarray,
    j_index: np.ndarray,
) -> None:
    """
    Compiled implementation of `skeletonize` (see `skeletonize` function).

    Args:
        nodes, edges: 2D bitmap and edge bitmask arrays.
        seeds: 8x2 int array for temp storage.
        queue, queue_start_stop: for BFS.
        touched, touched_start_stop: for BFS marking.
        i_index, j_index: coordinate arrays to scan.
    """
    for i, j in zip(i_index, j_index):
        remove_if_not_articulation(
            nodes,
            edges,
            seeds,
            queue,
            queue_start_stop,
            touched,
            touched_start_stop,
            i,
            j,
        )


def skeletonize(priority: np.ndarray, threshold: float) -> np.ndarray:
    """
    Skeletonize (thin) a boolean raster image, preserving topology.

    Args:
        priority: 2D numpy array to skeletonize; low values are removed first
        threshold: minimum priority to include in the graph at all; should be > 0

    Returns:
        edges: uint8 neighbor connectivity; `0` means no node at all, bitmasks of
            the following indicate which neighbors each node has:
                * 00000001 (  1) has a NW neighbor (i - 1, j - 1)
                * 00000010 (  2) has a N neighbor  (i - 1, j    )
                * 00000100 (  4) has a NE neighbor (i - 1, j + 1)
                * 00001000 (  8) has a W neighbor  (i    , j - 1)
                * 00010000 ( 16) has a E neighbor  (i    , j + 1)
                * 00100000 ( 32) has a SW neighbor (i + 1, j - 1)
                * 01000000 ( 64) has a S neighbor  (i + 1, j    )
                * 10000000 (128) has a SE neighbor (i + 1, j + 1)
    """
    nodes = priority > threshold
    edges = edges_from_nodes(nodes)

    # indices of all True elements
    j_index, i_index = np.meshgrid(np.arange(nodes.shape[1]), np.arange(nodes.shape[0]))
    i_index = i_index[nodes]
    j_index = j_index[nodes]

    # for prioritizing thinning order
    increasing_probability = np.argsort(priority[i_index, j_index])
    i_index = i_index[increasing_probability]
    j_index = j_index[increasing_probability]

    seeds = np.empty(
        (8, 2), dtype=np.int64
    )  # neighbors of a pixel, where to start the search

    queue_max_size = len(increasing_probability)
    queue = np.empty((queue_max_size, 2), dtype=np.int64)  # queue of (i, j)
    queue_start_stop = np.zeros(2, dtype=np.int64)  # [start, stop] for ring buffer

    touched = np.zeros(nodes.shape, dtype=np.int64)  # visitation stamps
    touched_start_stop = np.asarray(
        [1, 1], dtype=np.int64
    )  # [start, stop] window for stamps

    skeletonize_impl(
        nodes,
        edges,
        seeds,
        queue,
        queue_start_stop,
        touched,
        touched_start_stop,
        i_index,
        j_index,
    )
    return edges
