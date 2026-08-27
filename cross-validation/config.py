"""Shared configuration for the pass1 cross-validation analysis.

Everything here is pinned to reproduce the fit reported in Table 2 of the
SciPy paper, which came from notebooks/fit-to-hand-labeled-data.ipynb and was
announced in
https://github.com/dsi-rse/gully-map/pull/6#issuecomment-3384023049
"""

import pathlib

# ---------------------------------------------------------------- input paths
# The 6 derived metric rasters, as {metric}/{watershed}-{metric}.tif
DERIVED = pathlib.Path("~/Downloads/COPYOVER").expanduser()

# The hand-drawn truth, as {watershed}-mask.png and {watershed}-gully.png
HAND_LABELED = pathlib.Path(
    "~/Box/dsi-core/11th-hour/oaec/found-gullies/hand-labeled"
).expanduser()

# --------------------------------------------------------------- output paths
HERE = pathlib.Path(__file__).parent

# The extraction cache lives beside the hand-labeled inputs in Box, not in the
# repo: it is 2.5 GiB, it is derived data, and keeping it in Box means it
# survives deleting the working copy.  Note these are Box cloud files -- they
# hydrate on first read, so the first analyze.py after a fresh sync is slower.
CACHE = HAND_LABELED / "cross-validation-cache"
RESULTS = HERE / "results.json"
FIGURE = HERE / "cross-validation"  # .pdf and .png are appended

# ---------------------------------------------------------------- watersheds
# Order matches the `names` dict in fit-to-hand-labeled-data.ipynb and the
# paper's other per-watershed figure: alphabetical, except that
# "Lower Dry Creek Lower" precedes "Lower Dry Creek".
#
# Upper Matanzas Creek is deliberately absent.  It was hand-labeled but
# dropped in commit 2171e60 ("dropped Upper Matanzas Creek; fitting to 9
# watersheds"), after 1310395 found it was the only one in tension with the fit.
WATERSHEDS = [
    "Big Pepperwood Creek",
    "Dutch Bill Creek",
    "Flat Ridge Creek Buckeye",
    "Kolmer Gulch",
    "Lower Dry Creek Lower",
    "Lower Dry Creek",
    "Lower Salmon Creek",
    "Tombs Creek",
    "Upper Big Sulphur Creek",
]

# ------------------------------------------------------------------- metrics
# min15 MUST be first: it defines the NaN reference pattern that every other
# metric is checked against, and it defines the truth sharpening.
#
# The original notebook also read max15, max5 and low5, but none of those
# three enters a feature column -- they were only plotted.  Omitting them is
# exactly equivalent because all metrics share one NaN pattern (asserted in
# extract.py), so the mask is unchanged.
METRICS = ["min15", "low15", "highlow15", "min5", "highlow5", "mindisk"]

# ------------------------------------------------------------- feature spec
# `highlow15` IS (high15 - low15) and `highlow5` IS (high5 - low5); the names
# below are the notebook's, kept verbatim so they line up with Table 2.
# Column order must match cell 8 of the notebook exactly.
FEATURES = [
    "min15",
    "low15 - min15",
    "high15 - low15",
    "min5 - min15",
    "high5 - low5",
    "low15 * (high15 - low15)",
    "abs(mindisk)",
]


def build_features(m):
    """Stack the 7 feature columns from a dict of masked 1-D metric vectors.

    Replicates cell 8 of the notebook verbatim, including dtype: the inputs
    are float32 (as read from the GeoTIFFs) so the arithmetic is float32.
    sm.add_constant() later promotes to float64, which is what the original
    fit saw -- do not pre-convert, or the last digits will drift.
    """
    import numpy as np

    return np.stack(
        [
            m["min15"],
            m["low15"] - m["min15"],
            m["highlow15"],
            m["min5"] - m["min15"],
            m["highlow5"],
            m["low15"] * m["highlow15"],
            abs(m["mindisk"]),
        ]
    ).T


# ----------------------------------------------------------------- constants
# Truth sharpening: hand-drawn lines AND (min15 < SHARPEN).  Commit 127c460,
# "the problem was the training data; I sharpened it with (min15 < -3)".
SHARPEN = -3

# Detection threshold.  NOTE: production applied 1% to the *pass2* image
# (pass1 reconvolved at half resolution).  Reconvolution needs CuPy +
# numba.cuda, unavailable here, so we apply it to pass1 instead.  The
# resulting numbers are NOT comparable to the production pass2/pass3 numbers.
THRESHOLD = 0.01

# ------------------------------------------------------ published Table 2
# Full precision, from scripts/find_gullies.py lines 238-246, which cites
# the PR comment above as its source.
PUBLISHED = [
    ("(intercept)", -9.800051565013556),
    ("min15", -3.1639324806178912),
    ("low15 - min15", -0.7209343186388889),
    ("high15 - low15", 1.9421691573124356),
    ("min5 - min15", 0.19531310261020537),
    ("high5 - low5", -0.2707981230014441),
    ("low15 * (high15 - low15)", 0.6326805610644737),
    ("abs(mindisk)", -0.28814988058815305),
]

# Table 2 quotes 6 decimals, so that is the bar the reproduction must clear.
REPRODUCTION_TOL = 5e-7
