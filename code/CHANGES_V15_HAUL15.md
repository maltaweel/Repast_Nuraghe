# code_v15_haul15 (5 Nov 2026)

Decisions (specified by the authors, 5 Nov 2026): sites near their nearest outcrop quarry from it (near-site rule, ODD 7.6),
and the minimum haul `transport.min_haul_flatm` is 15 m instead of 100 m (the haul of a site on its outcrop and the floor of
every whole route; ODD 7.5). The v15 code also keeps the v13 social switches (ODD 7.15, 7.16).

Base: full_audited/code_v13 (frozen code/ + v13 social switches reputation / partner_choice / tie_imitation /
social_log / trusted_nodist; only alliance.py differs from code/). Change: alliance.py gets exactly the lines that
code_v14_nearface/v12_to_v14_nearface.patch adds (near_face_m(), Static.near, choose() face skip, signature hash
only when on); patch v13_to_v15_haul15.patch; the added lines are identical to the v14 patch (checked by diff). Every
other file is byte-identical to code_v13 / code_v14_nearface (CODE_V15_SHA256SUMS). Rule details:
CHANGES_V14_NEARFACE.md.

min_haul_flatm 15: NO code change. Every floor reads config transport.min_haul_flatm (model.py 285-286, alliance.py
trip() / carry, census_v12.py, sea.py, tools/sea_routes.py). No prepared table except the sea tables applies the
floor (preprocess / kbest_* / wl_inputs / haul_far store raw routes); the sea tables are rebuilt per config.

Off switches (near key absent / none / 0, social keys absent) = the audited v12 code path and signatures.
