"""Scenario key: family, code, readable name, one-sentence description, sources, changed parameters, FREE flags.

  python tools/scenario_guide.py config.yaml      -> output/scenario_guide.csv

Parameter values are read from config.yaml, so the key always matches the runs. Sources follow METHODS.md 8.2
(literature) and the review files (GEN = general_energetics_logistics.md, NUR = nuraghe_specific.md, line numbers).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nbcommon import load_config  # noqa: E402


def rows(cfg):
    L, S, A = cfg["lit_scenarios"], cfg["scenarios"], cfg["alliance"]
    tp = cfg["transport"]
    md = L["webster_md_per_tower"]
    qr, f, o, r = L["quarry_ph_m3"], L["facade"], L["oxen"], L["ramp"]
    g = L["geometry"]
    R = []
    add = lambda *x: R.append(dict(zip(["family", "code", "name", "description", "sources", "parameters", "free"], x)))
    add("baseline", "baseline", "Baseline: one community, full cooperation",
        "Every nuraghe is built by its own community of 50-200 cooperating builders, dragging stone from the nearest "
        + ("outcrop of its recorded building stone where known, otherwise the nearest " if cfg.get("stone_rule") == "hybrid" else "")
        + f"of the {len(cfg['stones4'] if cfg.get('stone_rule') == 'stones4' else cfg['allowed_stones'])} permitted outcrop types.",   # B9 "Webster 1991 (NUR 153-156, 181); UCL 2016 sledge experiment",
        f"{cfg['stone']['tonnes_per_tower']} t/tower; {tp['pull_kg_per_person']} kg per person; drag {tp['drag_speed_ms']} m/s; "
        f"{cfg['other_mandays_per_tower']} man-days/tower other work", "builder count rule (the authors' spec)")
    coop = {"none": ("No cooperation", "Nobody pools into crews: every household drags alone, so heavy blocks must be cut down to household size."),
            "low": ("Little cooperation (25%)", "One builder in four cooperates; the rest work only within their household of five."),
            "mixed": ("Half cooperate (50%)", "Half the builders cooperate freely, half only within their household."),
            "mostly": ("Mostly cooperative (75%)", "Three builders in four cooperate freely."),
            "full": ("Full cooperation", "Every builder cooperates; identical to the baseline."),
            "high": ("Full cooperation + inter-site help", "As full, and builders of a finished site walk to help the nearest unfinished site within 10 km."),
            "patchwork": ("Patchwork of communities", "Each site is either fully cooperative or not at all, with even odds.")}
    for k, (nm, ds) in coop.items():
        sc = S["list"][k]
        par = ", ".join(f"{a}={b}" for a, b in sc.items())
        add("cooperation", k, nm, ds, "the authors' specification (METHODS 7)", par +
            f"; household {S['household_size']}; split cost {S['split_cost_mh']} MH" +
            (f"; help radius {S['help_radius_m']:g} m" if sc.get("inter_site_help") else ""),
            "p_coop, household size, split cost, help radius")
    W = "Webster 1991 Table 1 (NUR 181)"
    lit = [
        ("webster", "Webster's stages (reference)", "The baseline with its 2,500 man-days split into Webster's quarrying, dressing, walling and lifting stages.", W,
         f"quarry {md['quarry']}, dress {md['dress']}, build {md['build']} md/tower; lift = {L['lift_share_of_build']:g} of build", "lift share"),
        ("S1a_scree", "Stone collected as fallen boulders/scree", "Stone is gathered from field clearance and scree instead of being broken from bedrock.",
         "Boswinkel 2021, Table 7.2; Turner 2020: 88 (GEN 48); field clearance in Sardinia (NUR 20-21)", f"quarrying {qr['scree']:g} ph/m3", "none"),
        ("S1b_joints_low", "Quarried along joints (low rate)", "Blocks are levered out of the outcrop along natural joints, at the cheaper end of the literature range.",
         "Boswinkel 2021, Table 7.2; Devolder 2013 (GEN 45, 200); Duos Nuraghes knoll quarry (NUR 27-31)", f"quarrying {qr['joints_low']:g} ph/m3", "none"),
        ("S1b_joints_high", "Quarried along joints (high rate)", "As above, at the costly end of the range.",
         "Boswinkel 2021, Table 7.2; Devolder 2013 (GEN 45, 200)", f"quarrying {qr['joints_high']:g} ph/m3", "none"),
        ("S2a_unworked", "Undressed (cyclopean) blocks", "Blocks are set as quarried, with no dressing at all.",
         "Boswinkel 2021, Table 7.20/8.3 (GEN 57); Webster 1991: 850-851 (NUR 39, 58)", "dressing = 0", "none"),
        ("S2b_fine", "Finely dressed outer face on complex nuraghi", "Complex nuraghi get an ashlar-like outer facing, costed as the facade premium over cyclopean walling.",
         "Boswinkel 2021, Table 8.3 (GEN 57, 199); isodomic masonry (NUR 61)",
         f"extra ({f['facade_ph_m3_mid']:g} - {f['cyclopean_ph_m3_mid']:g}) ph/m3 on facing {L['facing_thickness_m']:g} m thick, TWR_N >= {L['fine_min_towers']}",
         "facing thickness"),
        ("S3a_rails_tallow", "Sledge on tallowed timber rails", "Sledges run on tallow-greased timber rails, so each hauler moves three times the load.",
         "Richards & Whitby 1997: 237-239 (GEN 65)", "mu 0.1; cost raster rebuilt; 300 kg per person", "none"),
        ("S3b_rails_grease", "Sledge on greased rails", "Rails greased with fat, the lowest friction in the sources.",
         "Richards & Whitby 1997: 237-239 (GEN 65)", "mu 0.05; 600 kg per person", "none"),
        ("S3c_dry_ground", "Sledge on dry ground", "Wooden sledges dragged over dry, unprepared ground.",
         "de Haan 2009; Cotterell & Kamminga 1990 via Boswinkel 2021: 112-113 (GEN 64, 201)", "mu 0.38; 79 kg per person", "none"),
        ("S3d_rough", "Sledge on rough ground", "Dragging over rough ground, the top of the friction range.",
         "de Haan 2009 via Boswinkel 2021 (GEN 64, 201)", "mu 0.5; 60 kg per person", "none"),
        ("S3e_oxen", "Ox teams haul the sledges", "Pairs of oxen pull each block with one drover and one helper (plausible only from the Late Bronze Age).",
         "Barwell & Ayre 1982; DeLaine 1997 via Boswinkel 2021: 110-112 (GEN 69, 203); cattle rare before LBA (NUR 54)",
         f"{o['pull_N_per_ox']:g} N per ox; yoke efficiency {', '.join(f'{x:g}' for x in o['yoke_efficiency'])}; {o['speed_ms']:g} m/s; 2 men per team",
         "return speed; efficiency beyond 3 pairs"),
        ("S4a_lever", "Blocks levered up course by course", "Each block is levered up the tower one 0.9 m course at a time, with no ramp.",
         "Hodges 1989; de Haan 2009 via Boswinkel 2021: 116, 124 (GEN 77, 204)", f"{L['lever_ph_per_block_course']:g} ph per block per course",
         "tower geometry (15 m, cone 12 -> 8 m)"),
        ("S4b_ramp", "External earth ramp", "A single-sided earth ramp is built up to the top of each tower and removed afterwards.",
         "Boswinkel 2021: 122-123, Table 7.20 (GEN 68, 78, 205); Lilliu, Webster (NUR 69-72)",
         f"slope {r['slope']:g}; width {r['width_m']:g} m; dig {r['dig_ph_m3']:g} ph/m3; compaction {r['compact_kg_per_ph']:g} kg/ph; x{r['build_remove_factor']:g}",
         "width, earth density, carry distance"),
        ("S4c_internal_stair", "Internal stair used as the ramp", "Stones go up the intramural stair (Laner's hypothesis), so only the last metre is levered.",
         "Laner 1999: 30, 42-47 (NUR 79-81)", f"{L['lever_ph_per_block_course']:g} ph x (1 m / {g['course_height_m']:g} m) per block", "last-metre rule"),
        ("S5a_onsite", "Stone from the site itself", "All stone comes from the site or within 200 m, so every haul is the 100 m minimum.",
         "Webster 1991: 848, 852; Gallin 1989 (NUR 27, 45-46, 195-196)", "haul = 100 m everywhere", "none"),
        ("S5b_any_buildstone", "Any local building stone allowed", "Quarries may be any building-stone class, not only the authors' four, to show what the rule costs.",
         "lithology BUILDSTONE flag", "all 11 BUILDSTONE classes", "none"),
        ("S5c_complex_far", "Complex nuraghi fetch stone from 3 km", "Nuraghi with three or more towers take stone from the cheapest permitted outcrop at least 3 km away.",
         "Stiglitz et al. 2012 (S'Urachi, NUR 49, 198); Lo Schiavo et al. 2009 (NUR 50)",
         f"TWR_N >= {L['complex_far_min_towers']}; >= {L['complex_far_min_dist_m']:g} m", "TWR_N mapping"),
        ("S6_density", "Real stone density and hardness", "Blocks keep their volume but weigh what their rock weighs, and hard rock takes twice as long to quarry and dress.",
         "Turner 2020: 71 critique of Webster (GEN 136, 212)",
         "density " + ", ".join(f"{k} {v}" for k, v in L["density_kg_m3"].items()) + "; hardness x2 basalt, granite",
         "densities and hardness multipliers"),
        ("S7_webster_classes", "Webster's class totals", "Labour and stone follow Webster's totals for single, multi-tower and bastioned nuraghi instead of scaling with tower count.",
         "Webster 1991, Table 1 (NUR 156-158, 181-183)", "1,350 / 3,100 / 6,700 t; 3,600 / 8,400 / 18,000 md", "TWR_N -> class mapping"),
        ("S8_learning", "Learning across towers", "Each further tower of a complex is 15% cheaper to quarry, dress and build than the previous one.",
         "none (GEN 91: no archaeological rate)", f"learning rate {L['learning_rate']:g}", "learning rate"),
        ("LOW", "Lower bound (cheapest options)", "Scree + undressed blocks + tallowed rails + internal-stair lift + any building stone.",
         "combination of S1a, S2a, S3a, S4c, S5b", "see components", "as components"),
        ("HIGH", "Upper bound (costliest options)", "Joint quarrying (high) + fine facing + rough ground + earth ramp + real density and hardness.",
         "combination of S1b_high, S2b, S3d, S4b, S6", "see components", "as components"),
    ]
    for c, nm, ds, src, par, fr in lit:
        add("literature", c, nm, ds, src, par, fr)
    al = {"A0_alone": ("Communities build alone (reference)", "Each community builds its towers in its own season, learns from its own towers and pays to open quarry faces, but never asks neighbours."),
          "A1_ask": ("Asking for help, no trust", "Communities may ask neighbours within 10 km to quarry, dress, haul part-way or build; each request is accepted with even odds."),
          "A2_trust": ("Asking with reciprocity and trust", "As A1, but acceptance depends on trust, which grows when help is given and falls when a debtor refuses."),
          "A3_trust_learning": ("Trust + specialisation", "As A2, and helping builds skill, so frequent suppliers of a stage become cheaper at it."),
          "A4_trust_track": ("Trust + shared trackways", "As A2, and allies can build shared tallowed-rail tracks along their haul routes."),
          "A5_full": ("Full supply-chain cooperation", "Trust, specialisation, shared tracks and shared quarry faces together."),
          "A5_full_freerider": ("Full cooperation with free-riders", "As A5, but one community in five never helps anyone.")}
    for k, (nm, ds) in al.items():
        sc = dict(A["defaults"]); sc.update(A["list"][k] or {})
        par = ", ".join(f"{a}={b}" for a, b in (A["list"][k] or {}).items()) or "defaults"
        add("alliance", k, nm, ds, "the authors' request (METHODS 9); Wright 1936 (GEN 91); Richards & Whitby 1997 (GEN 65)",
            f"{par}; R {A['R_m'] / 1000:g} km; b {sc['b']:g}; season {A['season_days']} days",
            "trust and acceptance parameters, R, b, track cost, setup cost, learning parameters")
    PN = cfg.get("pre_networks")
    if PN:
        import pre_networks
        SZ = {"G3_canton": "cantons (one multi-tower seat + its single towers)", "G5": "groups of ~5 (FREE)",
              "G9_verify": "groups of ~9 (UNVERIFIED ~800-canton reading)", "G20_system": "territorial systems of ~20",
              "G50": "groups of ~50 (FREE)", "G133_tribe": "tribes of ~133 (cantons inside)"}
        SH = {"chain": "chained", "kmesh2": "each tied to 2 nearest", "kmesh4": "each tied to 4 nearest",
              "kmesh8": "each tied to 8 nearest", "hub": "hub-and-spoke (hub = biggest nuraghe)",
              "smallworld": "4-nearest with 10% ties rewired outside", "complete": "everyone tied to everyone"}
        SRC = {"G3_canton": "Ugas, summarised by Moravetti et al. 2009 p. ~361 (copyrighted)",
               "G20_system": "Perra 2008 via Trudu et al. 2016 (second-hand)",
               "G133_tribe": "Ugas via Moravetti et al. 2009 p. ~361", "G5": "FREE", "G50": "FREE",
               "G9_verify": "unverified in Ugas 2005 (sensitivity only)"}
        for code, sp in pre_networks.expand(cfg).items():
            if sp.get("all", 0) is None:
                add("pre-existing networks", code, "No pre-existing ties (check)", "The pre-network rules with no ties at all; must equal A0_alone.",
                    "verification", "empty tie sets", "none"); continue
            a = sp.get("all")
            extra = []
            if sp.get("reach", 1) > 1: extra.append(f"requests travel up to {sp['reach']} ties via brokers")
            if sp.get("trust"): extra.append("plus trust-based alliances (D7)")
            if sp.get("tie_loss_refusals"): extra.append(f"a tie is lost after {sp['tie_loss_refusals']} refusals (D8)")
            if sp.get("specialisation"): extra.append("with specialisation")
            if sp.get("tracks"): extra.append("with shared tracks")
            if a is not None and "partners" in a:
                nm = f"{a['partners']} nearest partners each"; src = "partners knob (FREE)"
                ds = f"Every community has fixed ties to its {a['partners']} nearest communities, regardless of groups."
            elif a is not None:
                nm = f"{SZ[a['groups']]}, {SH[a['shape']]}"
                if "seed_from" in a: nm += f"; groups centred {'on' if a['seed_from'] == 'on_outcrop' else 'away from'} outcrops"
                if "region" in a: nm += f"; only in the {a['region']}" + (" (top-density cells)" if a["region"] == "dense" else "")
                src = SRC[a["groups"]]
                ds = f"Ties fixed at the start inside {SZ[a['groups']]}, {SH[a['shape']]}; requests go only along ties (accepted with p {PN['p_tie']})."
            else:
                nm = "per-stage networks: " + ("wide stone supply, local building" if "wide_stone" in code else "local stone, wide building")
                src = "Ugas H6 'inter-cantonal stone supply' (catalogue D6)"
                ds = ("Separate tie sets: stone " + "/".join(str(sp["stone"][k]) for k in ("groups", "shape")) + ", moving "
                      + "/".join(str(sp["move"][k]) for k in ("groups", "shape")) + ", building " + "/".join(str(sp["build"][k]) for k in ("groups", "shape")) + ".")
            if extra:
                nm += "; " + "; ".join(extra)
            add("pre-existing networks", code, nm, ds, src, ", ".join(f"{k}={v}" for k, v in sp.items() if k != "all") or "reach 1",
                "p_tie, shape rules, group generator seed" + (", broker walk" if sp.get("reach", 1) > 1 else ""))
        add("pre-network sensitivity", "PS_*", "Pre-network sensitivity grid",
            "Every size x shape x reach (1-3) x learning (off/on) combination, 10 seeds each.", "as above", "see config", "all")
    G = A["sensitivity"]
    add("alliance sensitivity", "SENS_R*_b*_t*", "A5 sensitivity grid",
        "A5_full rerun for every combination of neighbourhood radius, learning rate and track cost (10 seeds each).",
        "as A5_full", f"R {G['R_m']} m; b {G['b']}; track {G['track_cost_mh_per_m']} MH/m", "all three are FREE")
    return pd.DataFrame(R)


if __name__ == "__main__":
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.yaml")
    df = rows(cfg)
    lit = set(cfg["lit_scenarios"]["list"]); co = set(cfg["scenarios"]["list"]); al = set(cfg["alliance"]["list"])
    assert lit <= set(df.code) and co <= set(df.code) and al <= set(df.code), "a scenario is missing from the key"
    out = os.path.join(cfg["paths"]["output_dir"], "scenario_guide.csv")
    df.to_csv(out, index=False)
    print(f"wrote {out}: {len(df)} rows ({df.family.value_counts().to_dict()})")
