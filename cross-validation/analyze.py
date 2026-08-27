"""Stage 2: reproduce the Table 2 fit, then run 9-fold leave-one-watershed-out CV.

Writes results.json for plot.py.  Expect 30-45 minutes; run it in the
background.

Usage:  python analyze.py
"""

import gc
import json
import sys
import time

import numpy as np
import statsmodels.api as sm
from sklearn.metrics import roc_auc_score

import config


def load_cache():
    if not (config.CACHE / "X.npy").exists():
        print(f"ERROR: no cache at {config.CACHE}. Run extract.py first.",
              file=sys.stderr)
        sys.exit(1)
    X = np.load(config.CACHE / "X.npy", mmap_mode="r")
    y = np.load(config.CACHE / "y.npy")
    groups = np.load(config.CACHE / "groups.npy")
    return X, y, groups


def fit_logit(X, y):
    """sm.Logit exactly as the notebook did it.

    X stays float32 (as read from the GeoTIFFs); sm.add_constant promotes the
    design matrix to float64.  That is precisely what the original fit saw, so
    do not pre-convert X or the last digits will drift.
    """
    return sm.Logit(y, sm.add_constant(X)).fit(disp=0)


def predict(params, X):
    """Logistic prediction from bare parameters, so no model object is retained.

    params[0] is the intercept.  Verified against fit.predict() in reproduce().
    """
    coefficients = np.asarray(params[1:], dtype=np.float64)
    return 1.0 / (1.0 + np.exp(-(float(params[0]) + X @ coefficients)))


def scores(y_true, p):
    """Recall and precision at config.THRESHOLD, plus AUC over all thresholds."""
    predicted = p > config.THRESHOLD
    true_positive = int(np.count_nonzero(predicted & y_true))
    false_positive = int(np.count_nonzero(predicted & ~y_true))
    false_negative = int(np.count_nonzero(~predicted & y_true))

    actual_positive = true_positive + false_negative
    flagged = true_positive + false_positive
    single_class = not y_true.any() or y_true.all()

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "recall": true_positive / actual_positive if actual_positive else float("nan"),
        "precision": true_positive / flagged if flagged else float("nan"),
        "auc": float("nan") if single_class else float(roc_auc_score(y_true, p)),
    }


def retvals(fit):
    return {
        "converged": bool(fit.mle_retvals.get("converged", False)),
        "iterations": int(fit.mle_retvals.get("iterations", -1)),
    }


def reproduce(X, y):
    """Refit on all 9 watersheds and compare against the published Table 2."""
    print("=" * 74)
    print(f"REPRODUCTION: refitting on all {len(y) / 1e6:.3f} M rows")
    print("=" * 74, flush=True)

    start = time.time()
    fit = fit_logit(X, y)
    elapsed = time.time() - start
    info = retvals(fit)
    print(f"converged={info['converged']} in {info['iterations']} iterations, "
          f"{elapsed:.1f} s\n")

    print(f"  {'term':26s} {'refitted':>19s} {'published':>19s} {'|diff|':>10s}")
    rows, worst = [], 0.0
    for (name, published), fitted in zip(config.PUBLISHED, fit.params):
        difference = abs(float(fitted) - published)
        worst = max(worst, difference)
        rows.append({"term": name, "refitted": float(fitted),
                     "published": published, "abs_diff": difference})
        print(f"  {name:26s} {float(fitted):19.15f} {published:19.15f} "
              f"{difference:10.2e}")

    # Same style of self-check the notebook used: confirm the bare-parameter
    # prediction path agrees with statsmodels', so the CV folds can skip
    # building a second design matrix.
    sample = np.random.default_rng(0).choice(len(y), 1000, replace=False)
    sample.sort()
    direct = predict(fit.params.tolist(), np.asarray(X[sample]))
    viasm = fit.predict(sm.add_constant(np.asarray(X[sample]), has_constant="add"))
    agreement = float(np.abs(direct - viasm).max())
    print(f"\n  predict() path agrees with statsmodels to {agreement:.2e}")
    assert agreement < 1e-12, "bare-parameter prediction path disagrees"

    print(f"\n  worst coefficient difference: {worst:.2e} "
          f"(tolerance {config.REPRODUCTION_TOL:.0e})")
    reproduced = worst < config.REPRODUCTION_TOL
    print("  ==> Table 2 REPRODUCED" if reproduced else
          "  ==> MISMATCH: does not reproduce Table 2")

    result = {"terms": rows, "max_abs_diff": worst, "reproduced": reproduced,
              "seconds": elapsed, **info}
    del fit
    gc.collect()
    return result


def cross_validate(X, y, groups):
    """Leave-one-watershed-out: fit on 8, score the 9th."""
    print("\n" + "=" * 74)
    print(f"9-FOLD LEAVE-ONE-WATERSHED-OUT CV (threshold {config.THRESHOLD})")
    print("=" * 74, flush=True)

    pooled = np.empty(len(y), dtype=np.float64)
    folds = []
    for index, watershed in enumerate(config.WATERSHEDS):
        test = groups == index
        train = ~test
        print(f"[{index + 1}/{len(config.WATERSHEDS)}] hold out {watershed} "
              f"({int(test.sum()) / 1e6:.3f} M rows) ...", end=" ", flush=True)

        start = time.time()
        fit = fit_logit(np.asarray(X[train]), y[train])
        params = fit.params.tolist()
        info = retvals(fit)
        del fit
        gc.collect()

        p = predict(params, np.asarray(X[test]))
        pooled[test] = p
        fold = scores(y[test], p)
        elapsed = time.time() - start
        del p
        gc.collect()

        print(f"recall {fold['recall']:.4f}  precision {fold['precision']:.4f}  "
              f"AUC {fold['auc']:.4f}  [{elapsed:.0f} s]", flush=True)

        folds.append({"watershed": watershed, "index": index,
                      "rows": int(test.sum()), "positive": int(y[test].sum()),
                      "coefficients": params, "seconds": elapsed,
                      **info, **fold})

    # Micro-average over all 9 held-out predictions pooled together -- NOT the
    # mean of the 9 per-watershed numbers.
    print("\npooling all held-out predictions ...", end=" ", flush=True)
    overall = scores(y, pooled)
    print(f"recall {overall['recall']:.4f}  precision {overall['precision']:.4f}  "
          f"AUC {overall['auc']:.4f}")

    means = {key: float(np.nanmean([f[key] for f in folds]))
             for key in ("recall", "precision", "auc")}
    print(f"mean of the 9 folds:            recall {means['recall']:.4f}  "
          f"precision {means['precision']:.4f}  AUC {means['auc']:.4f}")

    return folds, {"micro_average": overall, "mean_of_folds": means}


def main():
    X, y, groups = load_cache()
    print(f"cache: {X.shape} {X.dtype}, {100 * y.mean():.2f}% positive\n")

    reproduction = reproduce(X, y)
    folds, pooled = cross_validate(X, y, groups)

    config.RESULTS.write_text(json.dumps({
        "settings": {
            "threshold": config.THRESHOLD,
            "sharpen": config.SHARPEN,
            "features": config.FEATURES,
            "watersheds": config.WATERSHEDS,
            "total_rows": int(len(y)),
            "total_positive": int(y.sum()),
            "note": ("Threshold applied to pass1, not the production pass2 "
                     "image; reconvolution requires CuPy/numba.cuda. Truth is "
                     "the sharpened label (hand-drawn AND min15 < -3), "
                     "identical to the training label."),
        },
        "reproduction": reproduction,
        "folds": folds,
        "pooled": pooled,
    }, indent=2))
    print(f"\nWrote {config.RESULTS}")
    return 0 if reproduction["reproduced"] else 2


if __name__ == "__main__":
    sys.exit(main())
