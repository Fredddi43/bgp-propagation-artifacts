"""Structure probe of D-A39 family pickles: keys, types, lengths and status counters only.

Never prints per-event rows, AS sets or label-derived per-event values. Scalars are printed only for
whitelisted descriptive keys (status/kind/metric/reason/flags and contrast summary fields).
usage: python -I -B probe_structure.py <family-name> [...]
"""
import collections, hashlib, json, pickle, sys

D = "<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families"
SAFE_SCALARS = {"kind", "family", "status", "reason", "metric", "events", "mean_difference", "declares_primary_finding",
                "formal_tests", "intervals_computed", "selection_performed", "target_scope", "fits", "cohort",
                "comparator", "training_seed", "arm_id", "error", "model_input_distribution", "full_newperiod_coverage",
                "broader_training_reused_at_30_60_seconds", "scorable_events", "reference_events", "censored_events",
                "count", "n", "difference", "lower", "upper", "interval", "ci", "estimate", "method", "level",
                "repetitions", "bootstrap_seed", "blocks", "block", "contrast", "name", "label", "horizon_seconds"}
ROWLIKE = {"rows", "input_available_rows", "event_differences", "cohort_ids", "h3_cohorts", "per_event", "aligned", "predictions"}


def load(name):
    man = json.load(open(f"{D}/{name}.manifest.json"))
    raw = b"".join(open(f"{D}/{name}.pkl.part{i:04d}", "rb").read() for i in range(man["parts"]))
    assert hashlib.sha256(raw).hexdigest() == man["sha256_of_concatenated_parts"] and len(raw) == man["bytes"]
    return pickle.loads(raw)


def tname(v):
    return type(v).__module__ + "." + type(v).__name__ if type(v).__module__ != "builtins" else type(v).__name__


def describe(v, path="", depth=0, maxdepth=5, out=None):
    pad = "  " * depth
    if isinstance(v, dict):
        keys = list(v.keys())
        print(f"{pad}{path}: dict[{len(keys)}] keys={[str(k)[:60] for k in keys[:25]]}{' ...' if len(keys) > 25 else ''}")
        if depth >= maxdepth:
            return
        for k in keys[:40]:
            sub = v[k]
            ks = str(k)
            if ks in ROWLIKE:
                ln = len(sub) if hasattr(sub, "__len__") else "?"
                first = (sub[0] if isinstance(sub, list) and sub else None)
                fk = sorted(first.keys()) if isinstance(first, dict) else tname(first)
                print(f"{pad}  {ks}: {tname(sub)} len={ln} (row-like, values suppressed) first-keys={fk}")
                continue
            if isinstance(sub, (dict, list, tuple)):
                # for big homogeneous dicts (cells keyed by arm id) only describe the first two entries
                if isinstance(sub, dict) and len(sub) > 6 and all(isinstance(x, dict) for x in list(sub.values())[:6]):
                    print(f"{pad}  {ks}: dict[{len(sub)}] of dict; status counter="
                          f"{dict(collections.Counter(str(x.get('status')) for x in sub.values()))}")
                    for kk in list(sub)[:2]:
                        describe(sub[kk], f"{ks}[{str(kk)[:40]}]", depth + 2, maxdepth, out)
                    continue
                describe(sub, ks, depth + 1, maxdepth, out)
            elif ks in SAFE_SCALARS:
                print(f"{pad}  {ks} = {str(sub)[:300]!s}")
            else:
                print(f"{pad}  {ks}: {tname(sub)}")
    elif isinstance(v, (list, tuple)):
        print(f"{pad}{path}: {tname(v)} len={len(v)}")
        if v and depth < maxdepth:
            if all(isinstance(x, dict) for x in v[:50]):
                print(f"{pad}  status counter={dict(collections.Counter(str(x.get('status')) for x in v))}")
                describe(v[0], "[0]", depth + 1, maxdepth, out)
            else:
                print(f"{pad}  element types={dict(collections.Counter(tname(x) for x in v[:200]))}")
    else:
        print(f"{pad}{path}: {tname(v)}")


for name in sys.argv[1:]:
    print("=" * 30, name)
    obj = load(name)
    if isinstance(obj, dict) and obj.get("status") == "failed":
        # failed-family record: kind/family/status/error/traceback (code paths only)
        print({k: (v if k != "traceback" else "<traceback %d chars>" % len(v)) for k, v in obj.items()})
        continue
    describe(obj, name)
    sys.stdout.flush()
