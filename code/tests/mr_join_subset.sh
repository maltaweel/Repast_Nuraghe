#!/usr/bin/env bash
# join vs handover vs alone, REALISTIC 300-site subset, seeds 1-3, 1 rank (2 for the A5_full_P10 identity), ONE flock for
# the whole test (the base rerun chain holds the lock while it runs: this waits). Steps:
#   1 identity of every non-MR scenario (tests/identity_merged.sh body, inline, no nested lock)
#   2 MOST_REALISTIC_handover_P10/_P20/_P100 == the earlier MOST_REALISTIC_* subset runs (content of runs + parts)
#   3 MOST_REALISTIC_P10/_P20/_P100 (join); alone twins reused (unchanged signature) or rerun
#   4 comparison table + network need (join vs alone, handover vs alone), crew-limit / finish checks
set -uo pipefail
M=${NURAGHE_PROJECT:?set NURAGHE_PROJECT (see README)}/runs/2026-10-29-bugfix/merged
exec flock /tmp/nuraghe_dev.lock bash $M/tests/mr_join_subset_body.sh
