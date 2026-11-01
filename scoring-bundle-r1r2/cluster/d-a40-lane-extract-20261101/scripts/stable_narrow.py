"""Label-free narrowing of the D-A39 stable failure from the prepared (pre-label) stable checkpoint. Read-only.

The stable consumer scores cells in prepared['cells'] order and raised (via m.score_cell, i.e. a committed NON-persistence
cell) at the first scorable event with an empty stable-peer target AND an empty committed prediction. Labels are NOT
opened here. Using predictions only: an event with an empty prediction in a cell that was scored BEFORE the failing one
cannot have an empty scorable target at that horizon (that cell would have raised first). So the failing cell is a
committed non-persistence cell k whose candidate set cand_k = empty_pred_k - excluded_before_k[horizon] is non-empty,
and the failing event is in cand_k. This bounds, but cannot pin, the event without the target.
usage: python -I -B stable_narrow.py <out.json>
"""
import collections, hashlib, json, pickle, sys

P = ("<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-ckpt/"
     "stable-8b2ded7e985a2611c5bbe7e6.pkl")
WANT = {"bytes": 1479268630, "sha256": "3b057211e6fd1aacad37050e1dcd085bb9340e08cc426579a5526e055ef29b42",
        "fingerprint": "8b2ded7e985a2611c5bbe7e6ea64a678df48ece0e6d4b3dbc994923ad27988d5"}


class HR:
    def __init__(self, s):
        self.s, self.h, self.n = s, hashlib.sha256(), 0

    def read(self, n=-1):
        d = self.s.read(n); self.h.update(d); self.n += len(d); return d

    def readline(self, n=-1):
        d = self.s.readline(n); self.h.update(d); self.n += len(d); return d

    def readinto(self, b):
        k = self.s.readinto(b); self.h.update(memoryview(b)[:k]); self.n += k; return k


with open(P, "rb") as raw:
    st = HR(raw)
    header = pickle.load(st)
    prepared = pickle.load(st)
    trailing = st.read()
receipt = {"path": P, "bytes": st.n, "sha256": st.h.hexdigest(), "header": header, "trailing_bytes": len(trailing)}
receipt["matches_run_log"] = (st.n == WANT["bytes"] and st.h.hexdigest() == WANT["sha256"]
                              and header == {"fingerprint": WANT["fingerprint"], "stage": "stable"} and not trailing)
if not receipt["matches_run_log"]:
    raise SystemExit("checkpoint differs from the run-log receipt: " + json.dumps(receipt, default=str))

cells = prepared["cells"]
excluded = collections.defaultdict(set)
ABST = collections.defaultdict(list)
order, possible = [], []
for idx, (name, cell) in enumerate(cells.items()):
    role = cell.get("role", {})
    h = str(role.get("horizon_seconds"))
    entry = {"order": idx, "arm_id": name, "status": cell.get("status"),
             "role": {k: role.get(k) for k in ("family", "message_passing", "baseline", "horizon_seconds", "seed")}}
    if cell.get("status") != "committed":
        order.append(entry); continue
    persistence = role.get("baseline") == "persistence"
    preds = {p["event_id"]: p for p in cell["predictions"]}
    empty = []
    statuses = collections.Counter()
    for meta in cell["rows"]:                      # manifest row order = per_event_rows scoring order
        eid, status = meta["event_id"], meta.get("input_status", "available")
        statuses[status] += 1
        if status != "available" or not preds[eid].get("predicted_asns"):
            empty.append(eid)
    cand = [e for e in empty if e not in excluded[h]]
    ABST[h].append([m["event_id"] for m in cell["rows"] if m.get("input_status", "available") != "available"])
    entry.update(path="persistence()" if persistence else "m.score_cell", rows=len(cell["rows"]),
                 input_status_counts=dict(statuses), empty_prediction_events=len(empty),
                 empty_prediction_abstentions=sum(1 for m in cell["rows"] if m.get("input_status", "available") != "available"),
                 candidates_after_exclusion=len(cand))
    if cand and not persistence:
        possible.append({"order": idx, "arm_id": name, "role": entry["role"], "candidates": len(cand),
                         "candidates_in_scoring_order": cand})
    if cand and persistence:
        entry["note"] = "a persistence cell with candidates must have passed (the traceback is in m.score_cell)"
    excluded[h].update(empty)                      # if this cell passed, none of its empty-prediction events has an empty target
    order.append(entry)

out = {"checkpoint": receipt, "prepared_keys": sorted(prepared.keys()), "cells_in_scoring_order": order,
       "possible_failing_cells": possible,
       "first_possible_failing_cell": possible[0] if possible else None,
       "abstention_sets_identical_across_cells_per_horizon": {h: len({tuple(sorted(e for e in x)) for x in v}) == 1 for h, v in ABST.items()},
       "abstention_overlap_30_60": len(set(ABST["30"][0]) & set(ABST["60"][0])) if ABST.get("30") and ABST.get("60") else None,
       "note": ("label-free bound only: the failing cell is the FIRST entry of possible_failing_cells whose candidate set holds an "
                "event with an empty scorable stable-peer target; without opening labels it cannot be pinned further")}
with open(sys.argv[1], "w") as f:
    json.dump(out, f, indent=1, default=str)
print(json.dumps({"possible_failing_cells": [{k: v for k, v in p.items() if k != "candidates_in_scoring_order"} for p in possible],
                  "cells": len(order)}, default=str))
