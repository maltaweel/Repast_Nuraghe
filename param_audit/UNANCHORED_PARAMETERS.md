# Parameters with no literature anchor (2 Nov 2026)

From PARAM_AUDIT.md (70 parameters): 31 carry the label "Authors' assumption". Values are those of the full audited rerun.

## A. Need a source: 26 design choices
**Social / cooperation (the core of the alliance model)**
- A1 `alliance.R_m` = 10,000 m: radius for help requests, relays and imitation
- A2 `alliance.max_asks` = 3: candidates asked per task
- A3 `trust0 / delta_up / delta_down` = 0.5 / 0.1 / 0.2: starting trust; +0.1 when asked partner helps, -0.2 when a partner refuses after having received help (alliance.py:1123-1127)
- A4 `beta0..beta3` = 0 / 2 / 0.05 / 0.2: acceptance logit x = b0 + b1·trust - b2·backlog days - b3·distance km (alliance.py:1108)
- A5 `alliance_threshold` = 0.7: mutual trust needed to count an alliance
- A7 `alpha` = 0.5: value-update step (learning from outcomes)
- A8 `p_imit` = 0.3: probability of imitating a neighbour's technique, per tower
- A9 help mode "join" + specialisation: helpers add hands to the requester's stage; helping builds skill

**Building technique**
- B4 `block_min_kg` = 60: smallest block
- B9 limestone/marble density = 2,600 kg/m³ (no Sardinian measurement)
- B11 hardness factor basalt/granite = 2, others 1: multiplies quarrying and dressing hours
- Q3 quarry rule: jointed-outcrop rate on outcrops, scree off them
- Q4 dressing rule: none for 1 tower, Webster's rate for 2, fine dressing for 3+
- G6 lift share of Webster's building stage = 0.5
- G7 internal-stair lever = 1.0 m levered per course
- G8 lift rule: lever for corridor nuraghi, stair otherwise
- G9 learning rate (S8) = 0.15: tower i of a site costs 0.85^i

**Transport and quarries**
- H9 rails used above 1,000 m haul
- H10 friction μ = 0.3 used to build routes and haul costs
- H12 relay hand-off points 0.25 / 0.5 / 0.75 of the route; min 300 m
- H13 1.0 man-hour per cut of a heavy block
- K2 5 cheapest quarry faces per site
- K3 200 man-hours to open a new face
- S4 sea transfer 0.25 h per landing (Barresi 2016 suggests handling costs more; 1 h and 2 h runs queued)
- S5 sea bands, beach and hoist rules (2 km / 5 km, 10 m / 10°, 5 m, 2 km walk)

**Scheduling**
- T2 cohort membership: random per seed (no chronology used)

## B. Specified by the authors: 3
- T1 10% cohorts (P10)
- T3 90-day season
- K1 hybrid stone rule with 7 classes

## C. Technical, no source expected: 2 + 6
- X1 safety stop (20,000 seasons, never binding); X2 seeds 1-100
- Addendum (PARAM_AUDIT_ADDENDUM.md): sea grid factor, sea attach radius, max people sea time, raster all-touched, nodata snap radius, unreachable policy (GIS and numerical choices)
