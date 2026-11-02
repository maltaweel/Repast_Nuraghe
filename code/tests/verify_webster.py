"""Verification (c): a single-tower nuraghe with a ~200 m haul against Webster (1991).

Webster Table 1: ~3,600 man-days per single tower (= 28,800 man-hours at 8 h), of which ~1,100 man-days
are transport. We accept "ballpark" as total within 0.5x-1.5x of 3,600 man-days and transport between
100 and 1,100 man-days.

  python tests/verify_webster.py config.yaml      (after model.py has written output/)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402


def main(cfg_path):
    cfg = load_config(cfg_path)
    H = cfg["hours_per_day"]
    target = cfg["verify"]["webster_target_haul_m"]
    s = pd.read_csv(os.path.join(cfg["paths"]["output_dir"], "nuraghe_manhours_summary.csv"))
    c = s[(s.TWR_N == 1) & (s.haul_flag == "ok")]
    site = c.iloc[(c.haul_m - target).abs().argsort().iloc[0]]
    runs = pd.read_csv(os.path.join(cfg["paths"]["output_dir"], "nuraghe_manhours_runs.csv.gz"))
    r = runs[runs.UID == site.UID]
    tp = cfg["transport"]
    trip = (max(site.haul_flatm, tp["min_haul_flatm"]) / tp["drag_speed_ms"]
            + max(site.haul_m, tp["min_haul_flatm"]) / tp["return_walk_ms"]) / 3600 + tp["load_unload_h"]
    print(f"Verification (c): {site.UID} '{site.NAME}' ({site.COMUNE}), 1 tower, haul {site.haul_m:.0f} m "
          f"({site.haul_flatm:.0f} flat-m) from {site.quarry_stone}")
    print(f"  trip time per block {trip:.3f} h; blocks per run {r.n_blocks.min()}-{r.n_blocks.max()}; "
          f"builders {r.builders.min()}-{r.builders.max()}")
    tot_md = r.mh_total / H
    tr_md = r.mh_transport / H
    print(f"  total     mean {r.mh_total.mean():,.0f} man-hours = {tot_md.mean():,.0f} man-days "
          f"(range {tot_md.min():,.0f}-{tot_md.max():,.0f}); Webster ~3,600 man-days = 28,800 man-hours "
          f"-> ratio {tot_md.mean() / 3600:.2f}")
    print(f"  transport mean {r.mh_transport.mean():,.0f} man-hours = {tr_md.mean():,.0f} man-days "
          f"(range {tr_md.min():,.0f}-{tr_md.max():,.0f}); Webster ~1,100 man-days")
    print(f"  other (quarry/dress/build) {r.mh_other.mean() / H:,.0f} man-days; idle {r.mh_idle.mean() / H:,.1f} "
          f"man-days; days to completion {r.days.mean():.1f} ({r.days.min()}-{r.days.max()})")
    ok_total = 0.5 <= tot_md.mean() / 3600 <= 1.5
    ok_tr = 100 <= tr_md.mean() <= 1100
    print(f"  total in ballpark (0.5-1.5x): {ok_total}; transport within 100-1,100 man-days: {ok_tr}")
    # all 1-tower sites with hauls of 150-250 m, for context
    band = c[(c.haul_m >= 150) & (c.haul_m <= 250)]
    print(f"  all {len(band)} single-tower sites with 150-250 m hauls: median total "
          f"{band.mh_mean.median() / H:,.0f} man-days, median transport {band.tr_mean.median() / H:,.0f} man-days")
    print("WEBSTER CHECK", "PASSED" if ok_total and ok_tr else "OUT OF RANGE")
    return ok_total and ok_tr


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml") else 1)
