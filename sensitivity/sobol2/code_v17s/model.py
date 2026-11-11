"""Step 2 - repast4py agent-based model of nuraghe construction labour, with cooperation scenarios.

  mpirun -n 8 python model.py config.yaml [--scenario NAME|all] [--sites UID1,...] [--seeds 1-3]
                                          [--out DIR] [--parts-dir DIR] [--fresh] [--no-shapefile]

Without --scenario the baseline is run (everyone cooperates, no inter-site help) into output/.
With --scenario NAME (see `scenarios:` in config.yaml) the results go to output/scenarios/NAME/.

Agents (repast4py core.Agent subclasses, held in a repast4py SharedContext):
  Site    - one nuraghe; owns its blocks, its crews in transit and the quarry/build pool.
  Builder - one worker. Attributes: cooperator or not, household group, and the hour he is next free.
One repast4py schedule tick = one working day of hours_per_day hours.
Uncoupled scenarios: sites are dealt round-robin across ranks (COMM_WORLD).
Coupled scenario (inter_site_help): sites interact, so every rank simulates the WHOLE island for a
subset of the seeds (each model on MPI.COMM_SELF) - results are independent of the rank count.
Every site has its own random stream numpy.random.default_rng([seed, uid_int]).

The within-day logic (crew formation, trips, the coupled build pool) is the numba kernel site_day,
event-driven inside the day.
"""
import argparse
import gc
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd
from mpi4py import MPI
from numba import njit
from repast4py import context as ctx
from repast4py import core, schedule

import lit
import phasing
from nbcommon import load_config

# ----------------------------------------------------------------------------------- numba kernel
# indices into the per-site float64 state vector
S_DELM, S_POOL, S_POOLT, S_TRMH, S_ELAPSED, S_NDEL, S_DONE, S_DAY, S_TRIP, S_H, S_NBLK, S_NTR, S_TOTM = range(13)
NSTATE = 13


@njit(cache=True)
def site_day(st, mass, crew, bk_idx, bk_ptr, bk_end, cbusy, hh_n, hh_busy, tr_fin, tr_mass):
    """Advance one Site by one working day (hours 0..H). Event-driven within the day.

    cbusy  : per cooperating builder, the hour he is next free (relative to today's start).
    hh_n   : per non-cooperating household crew, its size (number of non-cooperating members).
    hh_busy: per household crew, the hour it is next free.
    Dispatch (repeated at every event): take the earliest block in queue order that SOME free crew can
    move (first-fit, per-crew-size FIFO buckets). Give it to the first free household crew big enough
    (hh_n >= crew needed); otherwise to `crew` free cooperators. A household always drags with all its
    members. A trip occupies its crew for trip_h hours and may run over into later days.
    Workers not on a trip (free cooperators + free households) work on the quarry/build pool, which may
    not run ahead of the delivered-mass fraction. Complete when all blocks are delivered and the pool done.
    With no households this is exactly the original all-cooperator kernel.
    """
    H = st[S_H]
    trip = st[S_TRIP]
    n = int(st[S_NBLK])
    ntr = int(st[S_NTR])
    B = cbusy.size
    NH = hh_n.size
    smax = bk_ptr.size - 1
    t = 0.0
    while True:
        # 1. deliveries arriving at or before t
        i = 0
        while i < ntr:
            if tr_fin[i] <= t:
                st[S_DELM] += tr_mass[i]
                st[S_NDEL] += 1.0
                ntr -= 1
                tr_fin[i] = tr_fin[ntr]; tr_mass[i] = tr_mass[ntr]
            else:
                i += 1
        alldel = int(st[S_NDEL]) == n
        if alldel and st[S_POOL] >= st[S_POOLT]:
            st[S_DONE] = 1.0
            st[S_ELAPSED] = st[S_DAY] * H + t
            break
        # 2. free crews take waiting blocks
        free = 0
        for b in range(B):
            if cbusy[b] <= t:
                free += 1
        while True:
            hmax = 0
            for h in range(NH):
                if hh_busy[h] <= t and hh_n[h] > hmax:
                    hmax = hh_n[h]
            capc = free if free > hmax else hmax
            if capc <= 0:
                break
            best = -1
            bs = -1
            top = capc if capc < smax else smax
            for s in range(1, top + 1):
                if bk_ptr[s] < bk_end[s]:
                    j = bk_idx[bk_ptr[s]]
                    if best < 0 or j < best:
                        best = j
                        bs = s
            if best < 0:
                break
            bk_ptr[bs] += 1
            c = crew[best]
            fin = t + trip
            hsel = -1
            for h in range(NH):
                if hh_busy[h] <= t and hh_n[h] >= c:
                    hsel = h
                    break
            if hsel >= 0:
                hh_busy[hsel] = fin
                k = hh_n[hsel]
            else:
                got = 0
                for b in range(B):
                    if cbusy[b] <= t:
                        cbusy[b] = fin
                        got += 1
                        if got == c:
                            break
                free -= c
                k = c
            tr_fin[ntr] = fin; tr_mass[ntr] = mass[best]
            ntr += 1
            st[S_TRMH] += k * trip
        # 3. next event: the earliest crew return, or the end of the day
        te = H
        for i in range(ntr):
            if tr_fin[i] < te:
                te = tr_fin[i]
        # 4. pool work by everyone not on a trip, capped by the delivered fraction
        workers = free
        for h in range(NH):
            if hh_busy[h] <= t:
                workers += hh_n[h]
        if alldel:
            cap = st[S_POOLT]
        else:
            cap = st[S_POOLT] * (st[S_DELM] / st[S_TOTM])
        room = cap - st[S_POOL]
        if workers > 0 and room > 0.0:
            work = workers * (te - t)
            if work >= room:
                if alldel:      # finishes inside this interval
                    st[S_POOL] = st[S_POOLT]
                    st[S_DONE] = 1.0
                    st[S_ELAPSED] = st[S_DAY] * H + t + room / workers
                    break
                st[S_POOL] = cap
            else:
                st[S_POOL] += work
        t = te
        if t >= H:
            break
    # carry trips over into the next day
    if st[S_DONE] == 0.0:
        for b in range(B):
            cbusy[b] = cbusy[b] - H if cbusy[b] > H else 0.0
        for h in range(NH):
            hh_busy[h] = hh_busy[h] - H if hh_busy[h] > H else 0.0
        for i in range(ntr):
            tr_fin[i] -= H
    st[S_NTR] = ntr
    st[S_DAY] += 1.0


# ----------------------------------------------------------------------------------- agents
class Builder(core.Agent):
    TYPE = 1

    def __init__(self, local_id, rank, site, coop, household):
        super().__init__(id=local_id, type=Builder.TYPE, rank=rank)
        self.site = site            # the site he currently works at (changes when helping)
        self.home = site.uid
        self.coop = coop            # cooperator (pools into any crew) or not (own household only)
        self.household = household  # household group number at the home site
        self.idx = -1               # index into site.cbusy (cooperator) or site.hh_busy (household crew)

    @property
    def busy_until(self):
        """Hour of the current day at which this builder is next free (0 = free now)."""
        return self.site.cbusy[self.idx] if self.coop else self.site.hh_busy[self.idx]

    def save(self):
        return (self.uid, self.home, self.coop, self.household)


class Site(core.Agent):
    TYPE = 0

    def __init__(self, gid, rank, rec, seed, P, sc, model):
        super().__init__(id=gid, type=Site.TYPE, rank=rank)
        self.gid = gid
        self.rec = rec
        rng = np.random.default_rng([seed, int(rec["uid_int"])])
        tw = int(rec["TWR_N"])
        b = P["builders"]
        base = round(b["base"] + b["per_extra_tower"] * (tw - 1))
        if sc.get("builders_rule"):                                # per-scenario work-party rule (one draw, as below)
            self.n_builders = B = lit.draw_builders(sc["builders_rule"], tw, rng)
        else:
            fac = rng.uniform(b["rand_min"], b["rand_max"])
            self.n_builders = B = int(min(b["max"], max(b["min"], round(base * fac))))
        # blocks: lognormal draws (clipped) until the cumulative mass reaches the site total
        s = P["stone"]
        litp = sc.get("lit")                                       # literature scenario (or None)
        if litp is not None and litp.get("mixed"):                 # REALISTIC: this site's own rules
            litp = lit.resolve_site(P, litp, rec, engine_b=True)  # no add4 L2 in engine B (add.4:41-42)
        if litp is None:
            target = s["tonnes_per_tower"] * 1000.0 * tw
            mf = 1.0
        else:                                                      # S6 density / S7 class tonnage
            mf = lit.mass_factor(P, litp, rec["quarry_stone"])
            target = lit.target_kg(P, litp, tw) * mf
        mu, sg, lo, hi = np.log(s["block_median_kg"] * mf), s["block_sigma"], s["block_min_kg"] * mf, s["block_max_kg"] * mf
        chunk = int(target / s["block_median_kg"]) + 16
        parts, tot = [], 0.0
        while tot < target:
            m = np.clip(rng.lognormal(mu, sg, chunk), lo, hi)
            parts.append(m); tot += m.sum()
        m = np.concatenate(parts)
        k = int(np.searchsorted(np.cumsum(m), target)) + 1      # first block at which cumsum >= target
        mass = np.ascontiguousarray(m[:k])
        # cooperation (drawn AFTER the blocks, so the block draw is the same in every scenario)
        if sc.get("site_coop_prob") is not None:                 # patchwork: whole site p=1 or p=0
            p = 1.0 if rng.random() < sc["site_coop_prob"] else 0.0
        else:
            p = float(sc["p_coop"])
        self.p_coop = p
        coop = rng.random(B) < p
        hs = int(sc["household_size"])
        hh_of = np.arange(B) // hs
        nonco = np.bincount(hh_of[~coop], minlength=hh_of.max() + 1)
        hh_ids = np.flatnonzero(nonco > 0)                         # households with >=1 non-cooperator
        self.hh_n = nonco[hh_ids].astype(np.int64)
        self.n_coop = int(coop.sum())
        tp = P["transport"]
        pull, v_drag, v_back, oxen = tp["pull_kg_per_person"], tp["drag_speed_ms"], tp["return_walk_ms"], None
        if litp is not None:
            pull, v_drag, v_back, oxen = lit.transport(P, litp)
            if oxen is not None:
                pull = 1e12                                        # human crew = drover + helper, never split
        # heavy blocks: split at the quarry into the fewest equal pieces whose crew fits the largest crew.
        # N1 (30 Oct b): the largest crew is the cooperator pool OR the largest non-cooperating household,
        # whichever is bigger (before: the pool alone whenever n_coop > 0, so a bigger household was ignored)
        maxcrew = max(self.n_coop, int(self.hh_n.max()) if self.hh_n.size else 0)
        crew0 = np.ceil(mass / pull)
        self.n_splits = 0
        sea_site = bool(sc.get("sea_kn")) and rec.get("mode") == "sea"          # S9: block carried by boat
        cap = float(P["sea"]["payload_kg"]) if sea_site else np.inf            # S9: craft payload (inf = no limit)
        if (crew0 > maxcrew).any() or (mass > cap).any():
            kk = np.maximum(1, np.ceil(mass / (pull * maxcrew))).astype(np.int64)
            if sea_site:
                kk = np.maximum(kk, np.ceil(mass / cap).astype(np.int64))
            while True:
                bad = (np.ceil(mass / kk / pull) > maxcrew) | (mass / kk > cap)
                if not bad.any():
                    break
                kk[bad] += 1
            self.n_splits = int((kk - 1).sum())
            mass = np.repeat(mass / kk, kk)                         # pieces keep the block's queue position
        self.mass = np.ascontiguousarray(mass)
        if oxen is None:
            self.crew = np.ceil(self.mass / pull).astype(np.int32)
            smax = int(np.ceil(hi / pull))
            self.yokes = None
        else:                                                      # S3e: an ox team per block
            self.crew = np.full(self.mass.size, int(oxen["men_per_team"]), np.int32)
            smax = int(oxen["men_per_team"])
            self.yokes = lit.oxen_yokes(self.mass, oxen)
        assert self.crew.max() <= maxcrew, "a block needs a bigger crew than any available"
        order = np.argsort(self.crew, kind="stable")              # queue order kept within each crew size
        self.bk_idx = order.astype(np.int32)
        cnt = np.bincount(self.crew, minlength=smax + 1)
        starts = np.concatenate([[0], np.cumsum(cnt)[:-1]])
        self.bk_ptr = starts.astype(np.int64).copy()
        self.bk_end = (starts + cnt).astype(np.int64)
        # trip time (hours): drag loaded + walk back empty + load/unload
        hf = max(rec["haul_flatm"], tp["min_haul_flatm"])
        hm = max(rec["haul_m"], tp["min_haul_flatm"])
        trip = hf / v_drag / 3600.0 + hm / v_back / 3600.0 + tp["load_unload_h"]
        hoist_ph = 0.0
        if sea_site:                                               # S9: quarry -> landing -> boat -> landing -> site
            import sea as seamod
            trip = seamod.trip_h(rec, P, sc["sea_kn"])
            hoist_ph = seamod.hoist_ph_per_block(rec, P)           # pulley at cliff landings, per block (pool)
        self.ox_h = 0.0 if self.yokes is None else float(2 * self.yokes.sum()) * trip   # oxen-hours, not man-hours
        H = float(P["hours_per_day"])
        st = np.zeros(NSTATE)
        if litp is None:
            if (P.get("v11") or {}).get("webster_day_fix"):      # v11: Webster's man-days at their source day length
                md = P["lit_scenarios"]["webster_md_per_tower"]
                parts = {k: md[k] for k in ("quarry", "dress", "build")}     # 500 + 1300 + 700 = other_mandays (2500)
                rest = P["other_mandays_per_tower"] - sum(parts.values())    # 0 with Webster's Table 1
                st[S_POOLT] = (sum(v * lit.md_hours(P, k) for k, v in parts.items()) + rest * H) * tw
            else:
                st[S_POOLT] = P["other_mandays_per_tower"] * H * tw
            self.stages = None
        else:                                                      # stage-explicit pool
            # NEW-1 (30 Oct): lever/stair lift is charged per lifted PIECE (blocks after crew/payload splitting);
            # k (drawn blocks) only fixes the mass; n_splits/split_cost_mh stay separate (below)
            self.stages = lit.stage_hours(P, litp, tw, rec["quarry_stone"], int(self.mass.size))
            st[S_POOLT] = self.stages["quarry"] + self.stages["dress"] + self.stages["build"] + self.stages["lift"]
        if self.n_splits:
            st[S_POOLT] += sc["split_cost_mh"] * self.n_splits
        if hoist_ph:
            st[S_POOLT] += hoist_ph * self.mass.size
        st[S_TRIP] = trip; st[S_H] = H; st[S_NBLK] = self.mass.size; st[S_TOTM] = self.mass.sum()
        self.st = st
        self.cbusy = np.zeros(self.n_coop)
        self.hh_busy = np.zeros(self.hh_n.size)
        ncap = self.n_coop + self.hh_n.size                        # max simultaneous trips
        self.tr_fin = np.zeros(ncap); self.tr_mass = np.zeros(ncap)
        # Builder agents
        self.workers = []            # cooperators currently working here (own + helpers)
        self.own_coops = []
        hh_index = {h: i for i, h in enumerate(hh_ids)}
        stride = max(256, int(b["max"]))                          # B12: unique ids for any builders.max (256 as before)
        for j in range(B):
            bld = Builder(gid * stride + j, rank, self, bool(coop[j]), int(hh_of[j]))
            if bld.coop:
                bld.idx = len(self.workers)
                self.workers.append(bld)
            else:
                bld.idx = hh_index[bld.household]
            model.context.add(bld)
        self.n_helpers = 0
        self.started = True          # phased runs (phase_frac): False until the site's phase begins
        self.pending = []
        self.mh_help = 0.0
        self.mh_walk = 0.0

    @property
    def done(self):
        return self.st[S_DONE] == 1.0

    def absorb_helpers(self):
        """Helpers that arrived overnight join the cooperator pool at the start of the day (all free)."""
        new = self.pending
        self.pending = []
        for bld in new:
            bld.site = self
            bld.idx = len(self.workers)
            self.workers.append(bld)
        self.n_helpers += len(new)
        self.cbusy = np.concatenate([self.cbusy, np.zeros(len(new))])
        ntr = int(self.st[S_NTR])
        cap = self.cbusy.size + self.hh_n.size
        for name, dt in (("tr_fin", np.float64), ("tr_mass", np.float64)):
            a = np.zeros(cap, dt); a[:ntr] = getattr(self, name)[:ntr]; setattr(self, name, a)

    def step(self):
        if self.pending:
            self.absorb_helpers()
        site_day(self.st, self.mass, self.crew, self.bk_idx, self.bk_ptr, self.bk_end,
                 self.cbusy, self.hh_n, self.hh_busy, self.tr_fin, self.tr_mass)
        if self.n_helpers:
            H = self.st[S_H]
            hours = self.st[S_ELAPSED] - (self.st[S_DAY] - 1.0) * H if self.done else H
            self.mh_help += self.n_helpers * hours

    def result(self):
        st = self.st
        own = self.n_builders * st[S_ELAPSED]
        total = own + self.mh_help + self.mh_walk
        return (st[S_ELAPSED], int(st[S_DAY]), total, st[S_TRMH], st[S_POOLT],
                _idle(total, st[S_TRMH], st[S_POOLT] + self.mh_walk), self.n_builders, int(st[S_NBLK]),
                st[S_TOTM], self.n_coop, self.n_splits, self.mh_help + self.mh_walk, self.n_helpers) + \
            ((np.nan,) * 5 if self.stages is None else
             (self.stages["quarry"], self.stages["dress"], self.stages["build"], self.stages["lift"], self.ox_h))

    def save(self):
        return (self.uid, int(self.rec["uid_int"]))


def _idle(total, transport, other):
    """Committed but unused builder-hours; float noise below 1e-6 h is reported as 0."""
    v = total - transport - other
    return 0.0 if abs(v) < 1e-6 else v


class Model:
    def __init__(self, comm, P, sc, local_recs, seed, neighbours=None):
        self.comm = comm
        self.rank = comm.Get_rank()
        self.context = ctx.SharedContext(comm)
        self.runner = schedule.init_schedule_runner(comm)
        self.max_days = int(P["max_days"])
        self.help = bool(sc.get("inter_site_help", False))
        self.walk_ms = float(sc.get("help_walk_ms", 1.4))
        self.neighbours = neighbours
        self.sites = []
        for gid, rec in local_recs:
            s = Site(gid, self.rank, rec, seed, P, sc, self)
            self.context.add(s)
            self.sites.append(s)
        self.by_gid = {s.gid: s for s in self.sites}
        self.active = list(self.sites)
        # phased construction (phasing.py; off unless sc['phase_frac']): only the current phase's sites are active
        self.phase_frac = sc.get("phase_frac")
        self.day = 0
        stop = self.max_days
        if self.phase_frac:
            n_all = comm.allreduce(len(self.sites), op=MPI.SUM)
            ph = phasing.phase_of(n_all, self.phase_frac, seed)
            self.n_phase = phasing.n_phases(self.phase_frac)
            self.cur_phase = -1
            for s in self.sites:
                s.phase = int(ph[s.gid]); s.started = False; s.start_day = -1
            self.active = []
            self.next_phase()
            stop = self.max_days * self.n_phase
        self.runner.schedule_repeating_event(1, 1, self.step)
        self.runner.schedule_stop(stop + 1)

    def next_phase(self):
        """Start the next phase: its sites become active on the next day (day numbers are island days, 1-based)."""
        self.cur_phase += 1
        self.active = [s for s in self.sites if s.phase == self.cur_phase]      # gid order
        for s in self.active:
            s.started = True
            s.start_day = self.day + 1

    def step(self):
        self.day += 1
        for s in self.active:
            s.step()
        finished = [s for s in self.active if s.done]          # gid order
        self.active = [s for s in self.active if not s.done]
        if self.help:
            for s in finished:
                self.send_helpers(s)
        if self.comm.allreduce(len(self.active), op=MPI.SUM) == 0:
            if self.phase_frac and self.cur_phase + 1 < self.n_phase:
                self.next_phase()
            else:
                self.runner.stop()

    def send_helpers(self, s):
        """All cooperators at a finished site walk to the nearest unfinished site within the radius."""
        if not s.workers:
            return
        nb_gid, nb_d = self.neighbours[s.gid]
        for g, d in zip(nb_gid, nb_d):                          # sorted by distance, then gid
            t = self.by_gid[g]
            if t.started and not t.done:                        # phased: never to a site whose phase has not begun
                n = len(s.workers)
                t.mh_walk += n * d / self.walk_ms / 3600.0
                t.pending.extend(s.workers)
                s.workers = []
                return
        s.workers = []                                          # nobody left to help nearby: they go home

    def run(self):
        self.runner.execute()
        if self.active or (self.phase_frac and self.cur_phase + 1 < self.n_phase):
            raise RuntimeError(f"rank {self.rank}: {len(self.active)} sites unfinished after max_days")
        return [s.result() for s in self.sites]


RES_COLS = ["elapsed_h", "days", "mh_total", "mh_transport", "mh_other", "mh_idle", "builders", "n_blocks",
            "stone_kg", "n_coop", "n_splits", "mh_help", "n_helpers",
            "mh_quarry", "mh_dress", "mh_build", "mh_lift", "ox_h"]
INT_COLS = ["seed", "gid", "days", "builders", "n_blocks", "n_coop", "n_splits", "n_helpers"]
# N1 (30 Oct b): the heavy-block split now uses max(cooperator pool, largest household). Hashed into run_signature
# ONLY for mixed cooperation (0 < p_coop < 1, not patchwork), the only runs whose results change; every other
# signature (and its cached parts) is unchanged.
SPLIT_VERSION = "2026-10-30b-maxcrew"


def neighbour_lists(haul, radius, travel=None, walk_ms=1.4):
    """Per site: other sites within radius (straight line), sorted by distance then gid.
    S9 (travel = sea.Travel): distance = min(straight line, sea travel time x walk speed), the walk-equivalent of
    min(walk, walk + boat + walk); same candidate set (straight-line radius), sorted by that distance."""
    from scipy.spatial import cKDTree
    xy = haul[["x", "y"]].to_numpy()
    tree = cKDTree(xy)
    out = []
    uid = haul.UID.to_numpy()
    for g, nb in enumerate(tree.query_ball_point(xy, r=radius)):
        nb = np.array([j for j in nb if j != g], dtype=np.int64)
        d = np.hypot(*(xy[nb] - xy[g]).T) if nb.size else np.zeros(0)
        if travel is not None and nb.size:
            d = np.array([travel.site_dist(uid[g], uid[j], dj, walk_ms) for j, dj in zip(nb, d)])
        o = np.lexsort((nb, d))
        out.append((nb[o], d[o]))
    return out


def parse_seeds(txt, cfg):
    if txt is None:
        return list(range(int(cfg["seeds"]["first"]), int(cfg["seeds"]["last"]) + 1))
    out = []
    for part in txt.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def scenario_params(cfg, name, family="coop"):
    """Merge the shared scenario parameters with one scenario's settings. name=None -> baseline.
    family 'lit': a literature scenario, always with full cooperation (p_coop = 1, no help)."""
    S = cfg["scenarios"]
    shared = {k: v for k, v in S.items() if k != "list"}
    sc = dict(shared)
    if family == "lit":
        sc.update({"p_coop": 1.0, "lit": lit.scenario(cfg, name)})
    else:
        base, frac = (name, None) if (name is None or name in S["list"]) else phasing.split_name(name)
        sc.update({"p_coop": 1.0} if base is None else S["list"][base])
        if frac is not None:                                     # NAME_P10 / NAME_P20: phased construction
            sc["phase_frac"] = frac
    return sc


def load_haul(cfg, a, path):
    haul = pd.read_csv(path)
    haul = haul[haul.haul_flatm.notna()]                         # 'exclude' policy drops unreachable sites
    if a.sites:
        haul = haul[haul.UID.isin(a.sites.split(","))]
    if a.first_n:
        haul = haul.iloc[: a.first_n]
    haul = haul.reset_index(drop=True)
    haul["uid_int"] = haul.UID.str.extract(r"(\d+)$")[0].astype(np.int64)
    assert haul.uid_int.is_unique
    return haul


def stale_parts(run_dir, seeds):
    """N4 (30 Oct b): part files on disk that lack a result column (written by older code under an unchanged
    signature). Returns a message naming the first stale file, or None. Counts are never invented."""
    for seed in seeds:
        mk = os.path.join(run_dir, f"seed_{seed:04d}.done")
        if not os.path.exists(mk):
            continue
        with open(mk) as fh:
            nr = int(fh.read().strip())
        for r in range(nr):
            fn = os.path.join(run_dir, f"seed_{seed:04d}.rank{r:03d}of{nr:03d}.csv")
            cols = set(pd.read_csv(fn, nrows=0).columns)
            miss = [c for c in RES_COLS if c not in cols]
            if miss:
                return (f"stale part file {fn}: missing column(s) {', '.join(miss)} (written by older code); "
                        f"rerun or use --fresh (or delete {run_dir})")
    return None


def run_signature(cfg, haul, sc):
    """Hash of everything that changes results: model + scenario parameters (not paths/seeds) and the sites."""
    keys = ["hours_per_day", "builders", "stone", "transport", "other_mandays_per_tower", "max_days"]
    h = hashlib.sha1(json.dumps({k: cfg[k] for k in keys}, sort_keys=True).encode())
    h.update(json.dumps({k: v for k, v in sc.items() if k != "coupled_max_ranks"}, sort_keys=True).encode())
    h.update(haul[["UID", "TWR_N", "haul_flatm", "haul_m"]].to_csv(index=False).encode())
    if sc.get("site_coop_prob") is None and 0.0 < float(sc.get("p_coop", 1.0)) < 1.0:   # N1: mixed cooperation
        h.update(SPLIT_VERSION.encode())
    if sc.get("sea_kn"):       # S9: the sea legs and the sea parameters
        import sea as seamod
        h.update(haul[seamod.SEA_COLS].to_csv(index=False).encode())
        h.update(json.dumps(cfg["sea"], sort_keys=True).encode())
    if (cfg.get("v11") or {}).get("webster_day_fix"):   # v11 (2 Nov 2026): Webster's man-days at source day lengths
        h.update(json.dumps(cfg["v11"], sort_keys=True).encode())
    if "lit" in sc:            # literature runs also depend on the lit_scenarios parameters and the quarry stone (S6)
        h.update(json.dumps({k: v for k, v in cfg["lit_scenarios"].items() if k != "list"}, sort_keys=True).encode())
        h.update(haul["quarry_stone"].to_csv(index=False).encode())
        if sc["lit"].get("mixed"):     # per-site rule inputs of a mixed scenario
            h.update(haul[["on_outcrop", "lit_haul_rule", "lit_type"]].to_csv(index=False).encode())
    # code_v16_final: the code version and the effective add4 settings (L2 acts in lit.resolve_site, season engine only
    # since the fix of 9 Nov 2026) are always hashed,
    # so part files written by older code (or under other add4 settings) are never reused
    h.update(json.dumps(lit.add4(cfg), sort_keys=True).encode())
    h.update(lit.CODE_VERSION.encode())
    if lit.lift_learning(cfg):                           # code_v17s: hashed only when on (default-off = code_v17)
        h.update(b"code_v17s sobol.lift_learning=True")
    return h.hexdigest()[:12]


def run_scenario(a, cfg, haul, name, family="coop"):
    comm = MPI.COMM_WORLD
    rank, size = comm.Get_rank(), comm.Get_size()
    sc = scenario_params(cfg, name, family)
    coupled = bool(sc.get("inter_site_help", False))
    seeds = parse_seeds(a.seeds, cfg)
    tag = name or "baseline"
    many = (a.scenario == "all") or (family == "lit" and a.lit == "all")
    sub = "scenarios_lit" if family == "lit" else "scenarios"
    if family == "lit":
        tag = "lit_" + name
        if sc["lit"].get("mixed"):                               # REALISTIC: per-site haul table (lit.mixed_haul)
            haul = lit.mixed_haul(cfg, sc["lit"], lambda p: load_haul(cfg, a, p))
        else:
            haul = load_haul(cfg, a, lit.haul_csv(cfg, sc["lit"]))   # S3/S5: the scenario's own haul table
        if sc["lit"].get("onsite"):                              # S5a: stone from the site itself
            haul["haul_flatm"] = 0.0
            haul["haul_m"] = 0.0
    if a.out:
        out_dir = os.path.join(a.out, name) if (many and name) else a.out
    else:
        out_dir = cfg["paths"]["output_dir"] if name is None else \
            os.path.join(cfg["paths"]["output_dir"], sub, name)
    os.makedirs(out_dir, exist_ok=True)
    cols = ["UID", "uid_int", "TWR_N", "haul_flatm", "haul_m", "quarry_stone"]
    if family == "lit" and sc["lit"].get("mixed"):              # REALISTIC: per-site rule inputs
        cols += ["on_outcrop", "lit_haul_rule", "lit_type"]
    travel = None
    if sc.get("sea_kn"):                                         # S9: the sea-aware haul table (same sites, same order)
        import sea as seamod
        haul = seamod.load_haul(haul, cfg, sc["sea_kn"])
        cols = cols + [c for c in seamod.SEA_COLS if c not in cols]
        if coupled:
            travel = seamod.Travel(cfg, sc["sea_kn"], haul.UID)
    recs = haul[cols].to_dict("records")
    if coupled:
        local = list(enumerate(recs))                            # every rank: the whole island ...
        model_comm = MPI.COMM_SELF                               # ... for its own seeds
        neighbours = neighbour_lists(haul, float(sc["help_radius_m"])) if travel is None else \
            neighbour_lists(haul, float(sc["help_radius_m"]), travel, float(sc.get("help_walk_ms", 1.4)))
    else:
        local = [(g, recs[g]) for g in range(rank, len(recs), size)]   # round-robin across ranks
        model_comm = comm
        neighbours = None

    # incremental, resumable output: one part file per (seed, rank) and a .done marker per seed
    base = a.parts_dir or os.path.join(cfg["paths"]["cache_dir"], "runs")
    run_dir = os.path.join(base, tag, run_signature(cfg, haul, sc))
    if rank == 0:
        os.makedirs(run_dir, exist_ok=True)
        done = set() if a.fresh else {s for s in seeds if os.path.exists(os.path.join(run_dir, f"seed_{s:04d}.done"))}
        stale = stale_parts(run_dir, sorted(done))               # N4: check resumed parts BEFORE running anything
    else:
        done = stale = None
    done, stale = comm.bcast((done, stale), root=0)
    if stale:
        raise SystemExit(stale)
    todo = [s for s in seeds if s not in done]
    # coupled: each rank holds the whole island (~1.9 GB), so only coupled_max_ranks ranks take seeds
    nwork = max(1, min(size, int(sc.get("coupled_max_ranks", size))))
    mine = (todo[rank::nwork] if rank < nwork else []) if coupled else todo
    if rank == 0:
        print(f"[{tag}] {len(haul)} sites, {len(seeds)} seeds, {len(done)} already on disk in {run_dir}, "
              f"{len(todo)} to run on {size} ranks ({f'seed-parallel on {nwork} ranks, whole island per rank' if coupled else 'sites round-robin'})",
              flush=True)
    t0 = time.time()
    for i, seed in enumerate(mine):
        model = Model(model_comm, cfg, sc, local, seed, neighbours)
        res = model.run()
        part = pd.DataFrame([(seed, g) + r for (g, rec), r in zip(local, res)], columns=["seed", "gid"] + RES_COLS)
        if sc.get("phase_frac"):                                 # phased runs only: phase and island start day per site
            part["phase"] = [model.by_gid[g].phase for g, _ in local]
            part["start_day"] = [model.by_gid[g].start_day for g, _ in local]
        mr, ms = (0, 1) if coupled else (rank, size)
        fn = os.path.join(run_dir, f"seed_{seed:04d}.rank{mr:03d}of{ms:03d}.csv")
        part.to_csv(fn + ".tmp", index=False)                  # pandas writes round-trip float repr
        os.replace(fn + ".tmp", fn)
        del model, res, part
        gc.collect()                                          # Site<->Builder reference cycles
        if coupled:
            with open(os.path.join(run_dir, f"seed_{seed:04d}.done"), "w") as fh:
                fh.write("1\n")
        else:
            comm.Barrier()
            if rank == 0:
                with open(os.path.join(run_dir, f"seed_{seed:04d}.done"), "w") as fh:
                    fh.write(f"{size}\n")
        if rank == 0 and (i == 0 or (i + 1) % 10 == 0 or i + 1 == len(mine)):
            print(f"  [{tag}] seed {seed}: done ({i + 1}/{len(mine)} on rank 0), {time.time() - t0:.1f} s", flush=True)
    comm.Barrier()
    if rank != 0:
        return
    print(f"[{tag}] model: {len(haul)} sites x {len(todo)} new runs on {size} ranks in {time.time() - t0:.1f} s")
    parts = []
    for seed in seeds:
        with open(os.path.join(run_dir, f"seed_{seed:04d}.done")) as fh:
            nr = int(fh.read().strip())
        for r in range(nr):
            parts.append(pd.read_csv(os.path.join(run_dir, f"seed_{seed:04d}.rank{r:03d}of{nr:03d}.csv")))
    df = pd.concat([q for q in parts if len(q)], ignore_index=True)   # ranks with no sites write empty parts
    stale = stale_parts(run_dir, seeds)                          # N4: never NaN-fill missing columns (checked above)
    if stale:
        raise SystemExit(stale)
    df[INT_COLS] = df[INT_COLS].astype(np.int64)
    assert len(df) == len(haul) * len(seeds), "missing rows in run parts"
    df["UID"] = haul.UID.to_numpy()[df.gid.to_numpy()]
    df["TWR_N"] = haul.TWR_N.to_numpy()[df.gid.to_numpy()]
    df = df.sort_values(["seed", "gid"]).reset_index(drop=True)
    df = df[["seed", "UID", "TWR_N"] + RES_COLS + (["phase", "start_day"] if sc.get("phase_frac") else [])]
    import report
    report.write_outputs(cfg, haul, df, out_dir, write_shp=not a.no_shapefile, scenario=name, family=family)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--scenario", help="scenario name from config.yaml, or 'all' (default: baseline)")
    ap.add_argument("--lit", help="literature scenario name from lit_scenarios, or 'all'")
    ap.add_argument("--alliance", help="alliance scenario name(s), 'all', 'sensitivity' or 'A0_verify'")
    ap.add_argument("--no-merge", action="store_true", help="alliance: write part files only")
    ap.add_argument("--pre", help="pre-existing network scenario(s), 'all' or 'sensitivity' (pre_networks.py)")
    ap.add_argument("--haul", help="baseline haul table (default cache/sites_haul.csv), e.g. cache/haul/sites_haul_stones7.csv")
    ap.add_argument("--sites", help="comma-separated UIDs (default: all)")
    ap.add_argument("--first-n", type=int, help="only the first N sites (benchmarking)")
    ap.add_argument("--seeds", help="e.g. 1-100 or 1,5,9 (default: from config)")
    ap.add_argument("--out", help="output dir (default: config output_dir[/scenarios/NAME])")
    ap.add_argument("--no-shapefile", action="store_true")
    ap.add_argument("--parts-dir", help="where per-run part files go (default: cache_dir/runs)")
    ap.add_argument("--fresh", action="store_true", help="ignore run parts already on disk and rerun all seeds")
    a = ap.parse_args()
    cfg = load_config(a.config)
    haul = load_haul(cfg, a, a.haul or os.path.join(cfg["paths"]["cache_dir"], "sites_haul.csv"))
    if a.pre:
        import alliance
        import pre_networks
        if a.pre == "all":
            names = list(pre_networks.expand(cfg))
        elif a.pre == "sensitivity":
            names = list(pre_networks.sens_expand(cfg))
        else:
            names = a.pre.split(",")
        seeds = parse_seeds(a.seeds, cfg)
        if a.pre == "sensitivity" and not a.seeds:
            s0, s1 = cfg["pre_networks"]["sensitivity"]["seeds"]
            seeds = list(range(s0, s1 + 1))
        root = a.out or os.path.join(cfg["paths"]["output_dir"], "scenarios_pre" + ("/sensitivity" if a.pre == "sensitivity" else ""))
        alliance.run(a, cfg, haul, names, seeds, out_root=root)
        return
    if a.alliance:
        import alliance
        if a.alliance == "all":
            names = list(cfg["alliance"]["list"])
        elif a.alliance == "sensitivity":
            names = alliance.sensitivity_names(cfg)
        else:
            names = a.alliance.split(",")
        seeds = parse_seeds(a.seeds, cfg)
        if a.alliance == "sensitivity" and not a.seeds:
            s0, s1 = cfg["alliance"]["sensitivity"]["seeds"]
            seeds = list(range(s0, s1 + 1))
        root = a.out or os.path.join(cfg["paths"]["output_dir"], "scenarios_alliance" +
                                     ("/sensitivity" if a.alliance == "sensitivity" else ""))
        alliance.run(a, cfg, haul, names, seeds, out_root=root)
        if MPI.COMM_WORLD.Get_rank() == 0 and not a.out and a.alliance in ("all", "sensitivity"):
            import report_alliance
            if a.alliance == "all":
                report_alliance.compare(cfg, names)
            else:
                report_alliance.sensitivity(cfg, names)
        return
    if a.lit:
        names = list(cfg["lit_scenarios"]["list"]) if a.lit == "all" else a.lit.split(",")
        for name in names:
            run_scenario(a, cfg, haul, name, family="lit")
        if a.lit == "all" and MPI.COMM_WORLD.Get_rank() == 0 and not a.out:
            import report
            report.compare_lit(cfg, names)
        return
    if a.scenario == "all":
        names = list(cfg["scenarios"]["list"])
    elif a.scenario:
        names = [a.scenario]
    else:
        names = [None]
    for name in names:
        run_scenario(a, cfg, haul, name)
    if a.scenario == "all" and MPI.COMM_WORLD.Get_rank() == 0 and not a.out:
        import report
        report.compare_scenarios(cfg, names)


if __name__ == "__main__":
    main()
