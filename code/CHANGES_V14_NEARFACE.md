# code_v14_nearface: near sites use their nearest face (5 Nov 2026)

Decision (specified by the authors, 5 Nov 2026): a site near its nearest outcrop quarries from it (there is no reason
to go further), and only the scenarios affected by the rule are rerun. Parameter `near_site_fixed_face_m` (ODD 7.6).

Base: full_audited/code (frozen audited v12). Only alliance.py changed (patch: v12_to_v14_nearface.patch); every
other file byte-identical (full_audited/CODE_V14_SHA256SUMS). Added: CODE_VERSION, this note, v14_chain.sh.

## Rule
Config key `quarry.near_site_fixed_face_m` (top-level `quarry:` block). Absent / none / 0 = the v12 code path.
In the v14 rerun configs (v14_nearface/configs/) it is 1000.
- near site = its dry-ground (mu 0.38) route length, haul table `haul/sites_haul_mu0.38.csv` column `haul_m` of
  that config's cache (the same quantity as the rails threshold long_min_haul_m), is <= the key. No mu 0.38 row:
  not near. Computed once per Static (Static.near).
- near site, per tower: face 0. In AllianceModel.choose(): the face dimension gets 0 with no epsilon draw, no Q
  argmax and no tie-break draw (the draws are SKIPPED, not drawn and discarded, so the site's stream moves on to the
  next dimension); imitation copies the neighbour's other dimensions but never the face. The per-tower imitation
  draw (p_imit) is unchanged. Sites over the threshold keep the choice among their k_quarries (+ sea) faces.
- fixed_actions (A0_verify, fixed_quarry_face=0) takes precedence as before (same value 0).
- The Q prior of all faces is still computed (no random draw; it is not used for a near site's face).
- Signature: NEARFACE_VERSION + the value are hashed only when the rule is on, so every run with the key off keeps
  its audited signature (identity test: v14_nearface/identity/).
