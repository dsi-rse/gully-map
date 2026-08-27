"""Stage 3: turn results.json into the paper figure.

A single horizontal bar chart of out-of-sample AUC per held-out watershed.

Recall and precision are computed and stored in results.json but not plotted.
Recall is ~1.0000 for every watershed -- 0.01 is a very permissive threshold, so
the panel carried almost no information.  Precision is 0.16-0.54, an order of
magnitude away, because the hand-drawn truth deliberately omits real gullies
(cliff edges were skipped), so genuine detections score as false positives.
Quote both in the text; AUC is the quantity that actually varies.

Usage:  python plot.py
"""

import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config

# Annotate each bar with its value.  Off by default to keep the figure clean.
SHOW_VALUES = False

FLOOR = 0.95          # x-axis runs FLOOR -> 1.0
COLOR = "C0"
FIGSIZE = (7.0, 2.4)  # inches: wide and short, rows packed tightly
BAR_HEIGHT = 0.62     # fraction of the row pitch

FONT_SIZE = 9
TICK_SIZE = 8


def nice_values(around):
    """Ascending 1/2/5 x 10^k values bracketing `around`."""
    exponent = int(np.floor(np.log10(around))) - 3
    return sorted(
        multiple * 10.0**power
        for power in range(exponent, exponent + 9)
        for multiple in (1, 2, 5)
    )


def ticks_within(floor, upper, step):
    """Every multiple of `step` inside [floor, upper].

    1.0 is a multiple of any 1/2/5 x 10^k step, so with the upper bound at 1 it
    is always a labelled tick -- the endpoint the figure needs.
    """
    first = int(np.ceil(round(floor / step, 9)))
    last = int(np.floor(round(upper / step, 9)))
    return [round(k * step, 10) for k in range(first, last + 1)]


def decimals_for(step):
    return max(0, int(-np.floor(np.log10(step))))


def choose_step(floor, upper, panel_inches):
    """Finest tick step whose labels still fit across `panel_inches`.

    Width-aware rather than a fixed cap: one wide panel affords many more ticks
    than the three narrow ones an earlier draft had.
    """
    for step in nice_values(upper - floor):
        if step > upper - floor:
            continue
        ticks = ticks_within(floor, upper, step)
        # ~0.6 em per character, plus 60% slack between labels
        label_inches = (decimals_for(step) + 2) * 0.60 * TICK_SIZE / 72.0
        if len(ticks) >= 2 and len(ticks) * label_inches * 1.6 <= panel_inches:
            return float(step)
    return float(upper - floor)


def main():
    if not config.RESULTS.exists():
        print(f"ERROR: {config.RESULTS} not found. Run analyze.py first.",
              file=sys.stderr)
        return 1

    results = json.loads(config.RESULTS.read_text())
    folds = {fold["watershed"]: fold for fold in results["folds"]}
    watersheds = [w for w in config.WATERSHEDS if w in folds]
    if len(watersheds) != len(config.WATERSHEDS):
        print(f"WARNING: only {len(watersheds)} of {len(config.WATERSHEDS)} "
              "watersheds present in results.json", file=sys.stderr)

    values = np.array([folds[w]["auc"] for w in watersheds], dtype=float)
    floor = FLOOR
    if values.min() < floor:
        print(f"WARNING: AUC minimum {values.min():.4f} is below the floor "
              f"{floor}; widening", file=sys.stderr)
        floor = float(np.floor(values.min() * 100) / 100)

    plt.rcParams.update({
        "font.size": FONT_SIZE,
        "xtick.labelsize": TICK_SIZE,
        "ytick.labelsize": FONT_SIZE,
        "axes.linewidth": 0.8,
    })

    figure, axis = plt.subplots(figsize=FIGSIZE, layout="constrained")
    positions = np.arange(len(watersheds))

    axis.barh(positions, values, height=BAR_HEIGHT, color=COLOR)

    # Longest watershed name, at ~0.6 em per character, is what the bars lose.
    names_inches = max(len(w) for w in watersheds) * 0.60 * FONT_SIZE / 72.0
    step = choose_step(floor, 1.0, FIGSIZE[0] - names_inches - 0.4)

    axis.set_xlim(floor, 1.0)
    ticks = ticks_within(floor, 1.0, step)
    axis.set_xticks(ticks)
    axis.set_xticklabels([f"{tick:.{decimals_for(step)}f}" for tick in ticks])
    axis.set_xlabel("out-of-sample AUC")

    axis.set_yticks(positions)
    axis.set_yticklabels(watersheds)
    axis.set_ylim(len(watersheds) - 0.5, -0.5)  # first watershed at the top

    axis.grid(axis="x", color="0.85", linewidth=0.5)
    axis.set_axisbelow(True)
    axis.tick_params(length=3)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)

    if SHOW_VALUES:
        for position, value in zip(positions, values):
            axis.text(value - 0.004 * (1.0 - floor) * 100, position,
                      f"{value:.4f}", va="center", ha="right",
                      fontsize=TICK_SIZE - 1, color="white")

    figure.savefig(f"{config.FIGURE}.pdf")
    figure.savefig(f"{config.FIGURE}.png", dpi=200)
    print(f"Wrote {config.FIGURE}.pdf and {config.FIGURE}.png")
    print(f"  AUC range [{values.min():.4f}, {values.max():.4f}]  "
          f"axis [{floor:g}, 1] step {step:g}  ({len(ticks)} ticks)")

    recall = [folds[w]["recall"] for w in watersheds]
    precision = [folds[w]["precision"] for w in watersheds]
    print(f"  (not plotted: recall {min(recall):.4f}-{max(recall):.4f}, "
          f"precision {min(precision):.4f}-{max(precision):.4f}; "
          "both in results.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
