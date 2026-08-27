# Cross-validation of the pass1 gully model

Self-contained analysis for the SciPy paper. Two things:

1. **Reproduction** — refit the pass1 logistic model on all 9 hand-labeled
   watersheds and check the 8 coefficients against **Table 2**.
2. **9-fold leave-one-watershed-out cross-validation** — out-of-sample recall,
   precision (1% threshold) and AUC per held-out watershed, plus the figure.

Nothing outside this directory is read or modified. The original fit is
`../notebooks/fit-to-hand-labeled-data.ipynb`; the published coefficients are in
`../scripts/find_gullies.py`, from
[PR #6 comment 3384023049](https://github.com/dsi-rse/gully-map/pull/6#issuecomment-3384023049).

## Results

**Table 2 reproduces exactly.** All 8 coefficients agree to within
**1.3e-11**, far inside the 6 decimals Table 2 quotes.

Leave-one-watershed-out, threshold 0.01 on pass1:

| held-out watershed | rows | positive | recall | precision | AUC |
|---|---|---|---|---|---|
| Big Pepperwood Creek | 12.512 M | 5.92% | 0.9999 | 0.3846 | 0.9847 |
| Dutch Bill Creek | 11.781 M | 4.40% | 1.0000 | 0.3513 | 0.9934 |
| Flat Ridge Creek Buckeye | 4.790 M | 10.42% | 0.9999 | 0.5117 | 0.9972 |
| Kolmer Gulch | 9.147 M | 4.57% | 0.9977 | 0.2834 | 0.9901 |
| Lower Dry Creek Lower | 29.471 M | 1.82% | 1.0000 | 0.4163 | 0.9994 |
| Lower Dry Creek | 4.204 M | 6.39% | 1.0000 | 0.4222 | 0.9983 |
| Lower Salmon Creek | 11.817 M | 2.11% | 0.9998 | 0.1599 | 0.9863 |
| Tombs Creek | 3.996 M | 10.55% | 1.0000 | 0.5413 | 0.9977 |
| Upper Big Sulphur Creek | 7.079 M | 10.84% | 1.0000 | 0.4248 | 0.9865 |
| **pooled (micro-average)** | **94.797 M** | **4.66%** | **0.9998** | **0.3708** | **0.9928** |

The pooled row is the micro-average over all 9 held-out prediction vectors
concatenated, not the mean of the 9 rows. Per-fold coefficients are in
`results.json` if coefficient stability is worth a sentence.

## Running it

```bash
python extract.py    # ~1.5 min, needs the rasters readable
python analyze.py    # ~12 min (11 min of it the 10 logistic fits)
python plot.py       # seconds, re-run freely to tweak the figure
```

| stage | reads | writes |
|---|---|---|
| `extract.py` | `~/Downloads/COPYOVER/{metric}/`, `~/Box/.../hand-labeled/` | `~/Box/.../hand-labeled/cross-validation-cache/` (2.5 GiB) |
| `analyze.py` | the cache in Box | `results.json` |
| `plot.py` | `results.json` | `cross-validation.pdf`, `.png` |

**`~/Downloads/COPYOVER/` (69 GiB) is no longer needed** — the cache holds only
the masked pixels, 2.5 GiB, and everything downstream reads the cache alone.
The cache lives in Box, next to the hand-labeled inputs, so it is not in the
repo and survives deleting the working copy. Being Box cloud files, they
hydrate on first read.

## What belongs in the paper

**The threshold is applied to pass1, not pass2.** Production thresholded the
*pass2* image: pass1 shrunk 2x and reconvolved with a directed kernel to link
linear threads. Reconvolution needs `../src/oaec_found_gully/convolution.py`,
which requires CuPy and `numba.cuda` and cannot run on this machine. So 1% is
applied to pass1 instead. **These numbers are not directly comparable to the
production pass2/pass3 thresholds.**

**The figure plots AUC only** (x-axis 0.95 to 1.00). Recall and precision are
computed and stored in `results.json`; quote them in the text.

- *Recall* is 0.9977-1.0000 across all nine watersheds. At a threshold as
  permissive as 0.01 that is close to a foregone conclusion, so it carries
  almost no per-watershed information and would render as nine full-width bars.
- *Precision* is 0.1599-0.5413, an order of magnitude from the other two, so it
  cannot share a near-1 axis. **The low value is a property of the labels, not
  the model**: the hand-drawn truth deliberately omits real gullies -- cliff
  edges were skipped on purpose -- so genuine detections are counted as false
  positives. A pooled precision of 0.37 is therefore *not* an estimate of the
  false-positive rate against ground truth, and should not be presented as one.

AUC is the quantity that actually varies (0.9847-0.9994) and it is threshold-free,
which makes it the honest headline given the pass1/pass2 substitution above.

**The figure's x-axis is truncated** -- it starts at 0.95, not 0. Every AUC sits
near 1, so a 0-based axis would compress all nine bars into near-identical
full-width blocks. Worth stating in the caption so bar *lengths* are not
over-read. 0.95 is deliberately rounder and lower than the data requires: a
data-driven floor came out at 0.982, which visually exaggerated a spread of
1.5 percentage points.

## Why only 6 of the 9 metrics

The notebook reads 9 derived metrics but only 6 enter a feature column:
`min15`, `low15`, `highlow15`, `min5`, `highlow5`, `mindisk`. `max15`, `max5`
and `low5` are read and histogrammed, never fitted.

Dropping them is *exactly* equivalent, but only because of a subtlety. Cell 4
of the notebook ANDs `mask` with `~np.isnan(data)` **progressively inside** the
metric loop while also taking `data[mask]` each iteration. That is
self-consistent only if every metric shares one NaN pattern — otherwise the
per-metric arrays get unequal lengths and `np.stack` in cell 8 raises. The
original run did not raise, so the assumption held.

`extract.py` asserts it explicitly, and the reproduction to 1.3e-11 is the
end-to-end proof: had dropping three metrics perturbed the mask, the
coefficients would not match.

`Upper Matanzas Creek` is excluded throughout — hand-labeled, but dropped in
commit `2171e60` after `1310395` found it was the only watershed in tension
with the fit.

## Details worth not breaking

- **94.797 M rows, not 99.1 M.** The PNG masks total 99.090 M pixels, but
  `Lower Salmon Creek`'s mask extends 4.293 M pixels into NaN and those rows
  drop out. The other 8 watersheds lose nothing. `extract.py` logs the loss
  per watershed rather than silently absorbing it.
- **The mask PNGs are mode `LA`, so channel 1 is *alpha*, not green.** The
  notebook's `np.asarray(file)[:, :, 1]` is alpha for LA images, and that is
  what produced Table 2. `extract.py` asserts `mode == "LA"` to pin the meaning
  against a future RGB conversion.
- **Features are built in float32**, exactly as the notebook did (they come
  straight from float32 GeoTIFFs). `sm.add_constant` then promotes the design
  matrix to float64. Pre-converting to float64 shifts the last digits and
  breaks the reproduction check.
- Truth is the **sharpened** label, `hand-drawn AND (min15 < -3)`, from commit
  `127c460`. Evaluation uses the same sharpened label as training.
- `extract.py` verifies each raster by reading its **last row**: `rsync
  --partial` leaves an interrupted transfer under its final name, so existence
  alone is not enough. (File size is not a usable check — there is a ~0.01%
  strip-table overhead on top of `width*height*4`.)
