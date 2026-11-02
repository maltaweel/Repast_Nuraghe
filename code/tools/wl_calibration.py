"""Calibration table: this model's stage rates vs Harris 2016, Erasmus 1965, Boswinkel 2021 (and Webster 1991, Lipo et
al. 2013) in common units, every conversion written out. Values are computed here from config + the MR_P10 summary row.

  python tools/wl_calibration.py CFG SUMMARY_CSV OUT_CSV

Columns: group, label, source, value, lo, hi, unit, conversion, ref (page), plot (1 = in f_wl_calib.png).
"""
import sys

import numpy as np
import pandas as pd
import yaml


def main(cfg_p, sum_p, out):
    cfg = yaml.safe_load(open(cfg_p))
    L, tp = cfg["lit_scenarios"], cfg["transport"]
    H = float(cfg["hours_per_day"])
    f = float(L["f_person_kgf"])
    v, w, ld = float(tp["drag_speed_ms"]), float(tp["return_walk_ms"]), float(tp["load_unload_h"])
    rho = float(L["webster_density_kg_m3"])
    m3 = cfg["stone"]["tonnes_per_tower"] * 1000.0 / rho                       # m3 per tower (block volume fixed)
    md = L["webster_md_per_tower"]
    s = pd.read_csv(sum_p).set_index("scenario").loc["MOST_REALISTIC_P10"]
    haul = pd.read_csv(cfg["paths"]["cache_dir"] + "/sites_haul.csv", usecols=["TWR_N"])
    towers = int(haul.TWR_N.sum())
    nan = np.nan
    R = []

    def r(group, label, source, value, unit, conversion, ref, lo=nan, hi=nan, plot=1):
        R.append(dict(group=group, label=label, source=source, value=value, lo=lo, hi=hi, unit=unit,
                      conversion=conversion, ref=ref, plot=plot))
    g = "Hauling crew (people per tonne)"
    r(g, "this model, sledge on dry ground", "this model", 1000 / (f / 0.38), "people/t", f"1000 kg / ({f:g} kgf / 0.38)",
      "METHODS (Boswinkel 2021: 111 pull; mu 0.38 de Haan via p. 114)")
    r(g, "this model, timber rails", "this model", 1000 / (f / 0.1), "people/t", f"1000 / ({f:g} / 0.1)",
      "METHODS (Richards & Whitby 1997: 237-239)")
    r(g, "Harris: haulers on a timber slipway", "Harris 2016", 10.0, "people/t", "10 haulers / ~1 t (mass: press)",
      "Harris 2016 (accepted manuscript)")
    r(g, "Harris: haulers + 14 slipway relayers", "Harris 2016", 24.0, "people/t", "(10 + 14) / ~1 t",
      "Harris 2016 (accepted manuscript)")
    r(g, "Boswinkel: sustained 125 N, mu 0.38", "Boswinkel 2021", 1000 * 0.38 * 9.81 / 125, "people/t",
      "1000 kg x 0.38 x 9.81 / 125 N", "Boswinkel 2021: 52 (125 N), 114 (0.38)")
    r(g, "Lipo et al.: walked statue", "Lipo et al. 2013", 18 / 4.35, "people/t", "18 people / 4.35 t",
      "Lipo et al. 2013 (via Lipo & Hunt 2025 abstract)")
    g = "Drag speed (m/s)"
    r(g, "this model, laden sledge", "this model", v, "m/s", "config transport.drag_speed_ms", "UCL 2016 experiment (press)")
    r(g, "Harris: maximum", "Harris 2016", 1.0, "m/s", "as stated", "Harris 2016 (accepted manuscript)")
    r(g, "Harris: 'about a mile an hour' (press)", "Harris 2016", 1609.344 / 3600, "m/s", "1,609 m / 3,600 s",
      "press reports of the experiment")
    r(g, "Boswinkel: loaded ox wagon", "Boswinkel 2021", 1670 / 3600, "m/s", "1.67 km/h", "Boswinkel 2021: 210")
    r(g, "Lipo et al.: walked statue", "Lipo et al. 2013", 100 / 2400, "m/s", "100 m / 40 min", "Lipo et al. 2013")
    g = "Hauling labour, drag + walk back (person-hours per tonne-km)"
    tk = (1000 / v + 1000 / w) / 3600
    r(g, "this model, dry ground", "this model", 1000 / (f / 0.38) * tk, "ph/t-km",
      f"12.67 people x (1 km / {v:g} m/s + 1 km / {w:g} m/s)", "config")
    r(g, "this model, rails", "this model", 1000 / (f / 0.1) * tk, "ph/t-km", "3.33 people x same times", "config")
    r(g, "Harris crew at our speeds", "Harris 2016", 10 * tk, "ph/t-km", "10 people x same times", "Harris 2016")
    r(g, "Harris + slipway relayers", "Harris 2016", 24 * tk, "ph/t-km", "24 people x same times", "Harris 2016")
    r(g, "Lipo et al.: walked statue", "Lipo et al. 2013", 18 / 4.35 * (2400 / 100 * 1000 / 3600 + 1000 / w / 3600),
      "ph/t-km", "4.14 people x (40 min per 100 m + walk back)", "Lipo et al. 2013")
    r(g, "Erasmus: carrying (~20 kg loads)", "Erasmus 1965", 5 / (4.0 * 0.05), "ph/t-km",
      "5-h day / (4 t x 0.05 km)", "Erasmus 1965: 284-93 via Thomas et al. 2021; loads p. 287 via Turner 2018: 200")
    r(g, "Pakkanen via Boswinkel (contract prices)", "Boswinkel 2021", 8.5, "ph/t-km",
      "0.7-1 man-days per t-km x 10 h (day length not given)", "Boswinkel 2021: 114 n. 76", lo=7.0, hi=10.0)
    g = "Short haul up to 200 m, whole trip (person-hours per tonne)"
    r(g, "this model, 100 m on dry ground", "this model", 1000 / (f / 0.38) * (100 / v / 3600 + 100 / w / 3600 + ld),
      "ph/t", f"12.67 x (100 m / {v:g} + 100 m / {w:g} m/s + {ld:g} h loading)", "config")
    r(g, "Erasmus: sled, 1,200 kg per 5-h day", "Erasmus 1965", 5 / 1.2, "ph/t", "5 h / 1.2 t (8-h day: 6.67)",
      "Erasmus 1965: 286-7 via Webster 1991: 852", lo=5 / 1.2, hi=8 / 1.2)
    r(g, "Webster: 1,100 man-days per tower (8-h days)", "Webster 1991", md["transport"] * H / 1350,
      "ph/t", f"1,100 md x {H:g} h / 1,350 t", "Webster 1991: 852-3 (Table 1)")
    g = "Loading + unloading (person-hours per tonne)"
    r(g, "this model, dry-ground crew", "this model", 1000 / (f / 0.38) * ld, "ph/t", f"12.67 people x {ld:g} h", "config")
    r(g, "this model, rails crew", "this model", 1000 / (f / 0.1) * ld, "ph/t", f"3.33 people x {ld:g} h", "config")
    r(g, "Boswinkel: levers, 6 ph per 5-t trip", "Boswinkel 2021", 6 / 5, "ph/t", "6 ph / 5 t",
      "Boswinkel 2021: 116, Table 7.6 p. 119")
    g = "Quarrying (person-hours per m3)"
    r(g, "this model, on its outcrop", "this model", float(L["quarry_ph_m3"]["joints_low"]), "ph/m3", "config S1b",
      "Boswinkel 2021 Table 7.2 p. 108 (low end)")
    r(g, "this model, collected stone", "this model", float(L["quarry_ph_m3"]["scree"]), "ph/m3", "config S1a",
      "Boswinkel 2021 Table 7.2 p. 108 (rubble)")
    r(g, "Boswinkel: cyclopean limestone", "Boswinkel 2021", 1 / 0.057, "ph/m3", "1 / (0.057-0.09 m3/ph)",
      "Boswinkel 2021 Table 7.2 p. 108", lo=1 / 0.09, hi=1 / 0.057)
    r(g, "Boswinkel: conglomerate (+15% waste)", "Boswinkel 2021", 1 / 0.03, "ph/m3", "1 / (0.03-0.048 m3/ph)",
      "Boswinkel 2021 Table 7.2 p. 108, p. 109", lo=1 / 0.048, hi=1 / 0.03)
    r(g, "Erasmus: wooden bar, 2,700 kg per 5-h day", "Erasmus 1965", 5 / (2.7 / rho * 1000), "ph/m3",
      f"5 h / (2.7 t / {rho:g} kg/m3) (8-h day: {8 / (2.7 / rho * 1000):.2f})", "Erasmus 1965: 286 via Webster 1991: 852",
      lo=5 / (2.7 / rho * 1000), hi=8 / (2.7 / rho * 1000))
    r(g, "Webster: 500 man-days per tower (8-h days)", "Webster 1991", md["quarry"] * H / m3, "ph/m3",
      f"500 md x {H:g} h / {m3:.1f} m3", "Webster 1991: 852-3 (Table 1)")
    g = "Walling / assembly, without lifting (person-hours per m3)"
    r(g, "this model (Webster, 8-h days, half is walling)", "this model", md["build"] * H * 0.5 / m3, "ph/m3",
      f"700 md x {H:g} h x 0.5 / {m3:.1f} m3", "Webster 1991: 852-3; lift share 0.5 (FREE)")
    r(g, "Webster read as 5-h days", "Webster 1991", md["build"] * 5 * 0.5 / m3, "ph/m3", f"700 x 5 x 0.5 / {m3:.1f}",
      "Erasmus 1965: 283 (5-h day)")
    r(g, "Erasmus: mortarless limestone masonry", "Erasmus 1965", 10.5, "ph/m3", "as stated (2.1 five-hour days)",
      "Erasmus 1965: 291 via Kaner 2022: 182")
    r(g, "Boswinkel: assembly, rubble to ashlar", "Boswinkel 2021", 1 / 0.1274, "ph/m3", "1 / (0.1-0.159 m3/ph)",
      "Boswinkel 2021 Table 7.11 p. 125", lo=1 / 0.159, hi=1 / 0.1)
    r(g, "Boswinkel: Mayes ashlar by block size", "Boswinkel 2021", 1 / 0.024, "ph/m3", "1 / (0.019-0.034 m3/ph)",
      "Boswinkel 2021: 125 (Mayes 1862: 24)", lo=1 / 0.034, hi=1 / 0.019)
    g = "Lever lift (person-hours per block per course)"
    r(g, "this model", "this model", float(L["lever_ph_per_block_course"]), "ph/block/course", "config",
      "Boswinkel 2021: 116, 124 (Hodges 1989; de Haan 2009)", plot=0)
    r(g, "Boswinkel", "Boswinkel 2021", 0.37, "ph/block/course", "as stated", "Boswinkel 2021: 124", plot=0)
    g = "Dressing a fine facing (person-hours per m3 of facing)"
    r(g, "this model (Table 8.3 totals, facade - cyclopean)", "this model",
      L["facade"]["facade_ph_m3_mid"] - L["facade"]["cyclopean_ph_m3_mid"], "ph/m3", "131.5 - 40.85",
      "Boswinkel 2021 Table 8.3 p. 144 (these are TOTAL costs)")
    r(g, "Boswinkel: dressing ashlar", "Boswinkel 2021", 59.5, "ph/m3", "1 / 0.0175 and 1 / 0.0162 (57-62)",
      "Boswinkel 2021: 120-121, Table 7.8", lo=1 / 0.0175, hi=1 / 0.0162)
    g = "All stages together (person-hours per m3 of wall)"
    r(g, "MR_P10 (this model, 100 seeds)", "this model", float(s.island_mh_mean) / (towers * m3), "ph/m3",
      f"{s.island_mh_mean / 1e6:.1f} M ph / ({towers:,} towers x {m3:.1f} m3)", "outputs/summary/wl_summary.csv")
    r(g, "Webster: 3,600 man-days per tower (8-h)", "Webster 1991", 3600 * H / m3, "ph/m3",
      f"3,600 md x {H:g} h / {m3:.1f} m3 (5-h day: {3600 * 5 / m3:.1f})", "Webster 1991: 852-3",
      lo=3600 * 5 / m3, hi=3600 * H / m3)
    r(g, "Boswinkel: cyclopean walls, Mycenaean", "Boswinkel 2021", (6.7 + 75.2) / 2, "ph/m3", "range 6.7-75.2",
      "Boswinkel 2021 Table 8.3 p. 144", lo=6.7, hi=75.2)
    g = "Working day (hours)"
    for lab, src, val, ref_ in (("this model", "this model", H, "config hours_per_day"),
                                ("Erasmus (heavy work, Mexico)", "Erasmus 1965", 5.0, "Erasmus 1965: 283 via Boswinkel 2021: 145"),
                                ("Boswinkel: conversions", "Boswinkel 2021", 10.0, "Boswinkel 2021: 132, 145-146")):
        r(g, lab, src, val, "h", "as stated", ref_, plot=0)
    pd.DataFrame(R).to_csv(out, index=False, float_format="%.6g")
    print(pd.DataFrame(R)[["group", "label", "value", "lo", "hi"]].to_string())


if __name__ == "__main__":
    main(*sys.argv[1:4])
