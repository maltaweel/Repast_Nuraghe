"""Workforce and years to build every nuraghe, per scenario (specified by the authors and
"how many years based on the population all of the nuraghes would be built in each scenario").

  python tools/workforce_years.py [--root REF/output] [--out dev_phase/output] [--families coop,lit,alliance,pre,baseline]

Per seed (then mean over seeds):
  workforce   W = sum over sites of builders (each nuraghe's own community; 'population per site', specified by the authors);
              also per tower count (W_TWR1..7, in workforce_by_towers.csv)
  island_mh   sum over sites of mh_total
  all-at-once rule: every nuraghe starts on day 1 with its own community, island done when the LAST site is done:
              years_max = max site days / 90 (season_days, Renfrew/Webster); years_p95 / years_med = the 95th percentile
              / median site days / 90; years_max_250 = max site days / 250 (long-calendar check)
  years_mh    = island_mh / (W x 8 h x 90 d): the labour-only bound (whole island workforce, perfectly pooled)
Alliance / pre-network scenarios: `days` is a site's OWN build span (finish_day - start_day + 1), so the all-at-once
columns are the same rule applied to their per-site spans. They ALSO have a native schedule: start_rate = 1/450 of the
sites start per season (random order), so the island finishes in ~450+ seasons; native_seasons = max finish_season;
native_peak_pop = max over seasons of the builders of the communities building in that season.
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _scen  # noqa: E402

H = 8


def per_seed(df, family):
    rows, tw_rows = [], []
    for seed, d in _scen.by_seed(df):
        days = d.days.to_numpy()
        B = d.builders.to_numpy().astype(np.int64)
        tw = d.TWR_N.to_numpy()
        r = {"seed": seed, "n_sites": len(d), "workforce": int(B.sum()), "island_mh": float(d.mh_total.sum()),
             "days_max": int(days.max()), "days_p95": float(np.percentile(days, 95)), "days_med": float(np.median(days))}
        if family in ("alliance", "pre"):
            r["native_seasons"] = int(d.finish_season.max())
            r["last_start_season"] = int(d.start_season.max())
            # native schedule: builders of the communities building in each season (start <= season <= finish)
            ss, fs = d.start_season.to_numpy(), d.finish_season.to_numpy()
            occ = np.zeros(int(fs.max()) + 2, np.int64)
            np.add.at(occ, ss, B); np.add.at(occ, fs + 1, -B)
            r["native_peak_pop"] = int(np.cumsum(occ).max())
        rows.append(r)
        for t in np.unique(tw):
            k = tw == t
            tw_rows.append({"seed": seed, "TWR_N": int(t), "n_sites": int(k.sum()), "workforce": int(B[k].sum()),
                            "mh": float(d.mh_total.to_numpy()[k].sum()), "days_max": int(days[k].max())})
    return pd.DataFrame(rows), pd.DataFrame(tw_rows)


def summarise(fam, name, ps):
    sd = _scen.SEASON_DAYS
    r = {"family": fam, "scenario": name, "seeds": len(ps), "n_sites": int(ps.n_sites.iloc[0]),
         "workforce": ps.workforce.mean(), "workforce_min": ps.workforce.min(), "workforce_max": ps.workforce.max(),
         "island_mh": ps.island_mh.mean(),
         "years_max": (ps.days_max / sd).mean(), "years_max_seedmin": ps.days_max.min() / sd,
         "years_max_seedmax": ps.days_max.max() / sd,
         "years_p95": (ps.days_p95 / sd).mean(), "years_med": (ps.days_med / sd).mean(),
         "years_max_250": (ps.days_max / 250.0).mean(),
         "years_mh": (ps.island_mh / (ps.workforce * H * sd)).mean(),
         "days_max": ps.days_max.mean(), "days_p95": ps.days_p95.mean(), "days_med": ps.days_med.mean()}
    if "native_seasons" in ps:
        r["native_seasons"] = ps.native_seasons.mean()
        r["native_seasons_max"] = ps.native_seasons.max()
        r["native_peak_pop"] = ps.native_peak_pop.mean()
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=_scen.REF_ROOT)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output"))
    ap.add_argument("--families", default="baseline,coop,lit,alliance,pre")
    a = ap.parse_args()
    fams = set(a.families.split(","))
    os.makedirs(a.out, exist_ok=True)
    o0 = _scen.oom_kill()
    rows, tws, seeds_all = [], [], []
    t0 = time.time()
    for fam, name, path in _scen.scenarios(a.root):
        if fam not in fams:
            continue
        df = _scen.load_runs(path, fam)
        ps, tw = per_seed(df, fam)
        del df
        rows.append(summarise(fam, name, ps))
        ps.insert(0, "scenario", name); ps.insert(0, "family", fam)
        seeds_all.append(ps)
        g = tw.groupby("TWR_N").agg(n_sites=("n_sites", "mean"), workforce=("workforce", "mean"), mh=("mh", "mean"),
                                    days_max=("days_max", "mean")).reset_index()
        g.insert(0, "scenario", name); g.insert(0, "family", fam)
        tws.append(g)
        print(f"  {fam:8s} {name:28s} W={rows[-1]['workforce']:9,.0f} MH={rows[-1]['island_mh']:14,.0f} "
              f"yrs max/p95/med={rows[-1]['years_max']:.2f}/{rows[-1]['years_p95']:.2f}/{rows[-1]['years_med']:.2f}"
              + (f" native={rows[-1]['native_seasons']:.1f} seasons, peak pop {rows[-1]['native_peak_pop']:,.0f}" if "native_seasons" in rows[-1] else "")
              + f"  [{time.time() - t0:.0f} s, peak {_scen.rss_mb()} MB]", flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(a.out, "workforce_years.csv"), index=False, float_format="%.4f")
    pd.concat(seeds_all).to_csv(os.path.join(a.out, "workforce_years_by_seed.csv"), index=False, float_format="%.4f")
    tw = pd.concat(tws)
    tw.to_csv(os.path.join(a.out, "workforce_by_towers.csv"), index=False, float_format="%.2f")
    wide = tw.pivot_table(index=["family", "scenario"], columns="TWR_N", values="workforce").add_prefix("W_TWR")
    wide.reset_index().to_csv(os.path.join(a.out, "workforce_by_towers_wide.csv"), index=False, float_format="%.1f")
    print(f"wrote {a.out}/workforce_years.csv ({len(res)} scenarios); peak RSS {_scen.rss_mb()} MB; "
          f"oom_kill {o0} -> {_scen.oom_kill()}")


if __name__ == "__main__":
    main()
