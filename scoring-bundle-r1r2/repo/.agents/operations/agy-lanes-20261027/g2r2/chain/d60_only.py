"""Owner decision: the frozen-2025 SAGE+history arm (evaluation arm ``frozen_sage_on``) is evaluated at 60 s ONLY.

In-process wrapper in the style of deviations D-A13..D-A21 (see qwen/q11-deviations/DEVIATIONS-LEDGER.md): after the
pinned module is loaded, named module functions are replaced by *source-patched copies of the pinned functions*.
No pinned or published file is edited; the module file bytes (and hence the sha the R2 runner pins) are unchanged.

Why source-patched copies and not wrapper closures: ``count/evaluate.py::private_primary`` (used by the R2 persistence
runner and by ``compose.evaluate``) copies every module function whose ``__globals__`` is the module dict into a private
module, so that lookups such as ``role_arm`` resolve to the private copy (which narrows baseline variants, D-A13). The
patched functions are therefore compiled in the module's own namespace and keep resolving every helper through module
globals. Every patch asserts that its anchor text occurs exactly once; an unmatched anchor raises, the pinned module is
not left half patched (all patches are compiled before any name is replaced).

Entry points
  install(module=None)                  forecast_custodian_eval: derive_new_period_arms, _contrast_families, evaluate_new_period
                                        (call BEFORE anything copies the module: private_primary, make_arm_spec, runner)
  install_runner(runner_module)         R2 persistence runner ``evaluate``: retained arms excluded from evaluation count as handled
  install_report_facts(facts, release)  forecast_full_report_facts.collect: 51 instead of 56 primary identities;
                                        forecast_release_facts.collect: Holm family size = len(contrasts) + declared placeholders
  excluded_ids(custody_spec)            ids of the frozen d30 cells (executable arms and retained failures) left out of evaluation

Semantics (decision, not a re-derivation): every (frozen_sage_on, 30) cell is left out of the evaluation, whether it is the
retained failure (seed 0) or an executable arm (seeds 1-4); the custody spec must record the seed-0 d30 cell in
``retained_failures`` (``_D60_CFG['require_failure_record']``). frozen_sage_on keeps all its training seeds at 60 s and
check_seed_pairing still requires them to equal the other learned arms' seeds there. All other arms are untouched.
C5/C6 at 30 s and C5-native at 30 s are reported as ``not_available`` under ``d60_only_deviation``, never computed.
Holm: the registered family sizes (12 primary/secondary families, 4 whole-system) are kept; each unavailable contrast
enters the step-down as a placeholder p = 1.0 that is never reported (conservative; no estimate is fabricated). Set
``HOLM_PAD = False`` BEFORE install() for Holm over the available contrasts only (a root decision).
"""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

PINNED_EVAL_SHA256 = "1619b3286cc5a61c6ceb4aee1ae7bb32c78262c47faf5ea4730c3b647f6fe078"
HOLM_PAD = True
MARK = "_D60_ONLY_INSTALLED"

HELPERS = '''
_D60_CFG = {"require_failure_record": True, "holm_pad": __HOLM_PAD__}
_D60_REASON = ("frozen_sage_on is evaluated at 60 s only (owner decision); its 30 s cells are not part of the "
               "evaluation, so no value exists and none is computed")


def _d60_horizons(name):
    return (60,) if name == "frozen_sage_on" else HORIZONS


def _d60_is_excluded(role):
    try:
        name = role_arm(role)
    except ValueError:
        return False
    return name == "frozen_sage_on" and role.get("horizon_seconds") == 30


def _d60_excluded_ids(custody_spec):
    ids = []
    for key in ("arms", "retained_failures"):
        for arm in custody_spec.get(key) or []:
            role = arm.get("role") if isinstance(arm, dict) else None
            if isinstance(role, dict) and _d60_is_excluded(role):
                ids.append(arm["arm_id"])
    return ids


def _d60_require_failure_record(custody_spec):
    if not _D60_CFG["require_failure_record"]:
        return
    failed = [a for a in custody_spec.get("retained_failures") or []
              if isinstance(a, dict) and isinstance(a.get("role"), dict) and _d60_is_excluded(a["role"])]
    if [a["role"].get("seed") for a in failed] != [0]:
        raise ValueError("d60-only: the freeze must record exactly the (frozen_sage_on, 30 s, seed 0) cell as a retained failure")


def _d60_pad(unavailable):
    return len(unavailable) if _D60_CFG["holm_pad"] else 0


def _d60_holm(p_values, padding):
    from .forecast_ranking import holm
    padded = dict(p_values)
    for i in range(padding):
        padded[("unavailable", i)] = 1.0
    adjusted = holm(padded)
    return {k: adjusted[k] for k in p_values}
'''

# (function name, [(anchor, replacement), ...]); every anchor must occur exactly once in the pinned source.
PATCHES = {
    "derive_new_period_arms": [
        ("    entries, seen = [], {}\n", "    entries, seen, excluded = [], {}, []\n"),
        ("            raise ValueError(f\"{arm['arm_id']}: undeclared horizon\")\n",
         "            raise ValueError(f\"{arm['arm_id']}: undeclared horizon\")\n"
         "        if name == \"frozen_sage_on\" and horizon == 30:\n"
         "            excluded.append(arm['arm_id'])  # d60-only: no 30 s cell of this arm is evaluated\n"
         "            continue\n"),
        ("    missing = [a for a in NEW_PERIOD_ARMS if set(derived.get(a, {})) != {\"30\", \"60\"}]\n",
         "    missing = [a for a in NEW_PERIOD_ARMS\n"
         "               if set(derived.get(a, {})) != ({\"60\"} if a == \"frozen_sage_on\" else {\"30\", \"60\"})]\n"),
        ("    return derived\n", "    _d60_require_failure_record(custody_spec)\n    return derived\n"),
    ],
    "_contrast_families": [
        ("    if set(arms) < needed or any(set(arms[a]) != set(HORIZONS) for a in needed):\n",
         "    if set(arms) < needed or any(set(arms[a]) != set(_d60_horizons(a)) for a in needed):\n"),
        ("            for per_event in arms[name][delta]:\n                mask =",
         "            for per_event in arms[name].get(delta, ()):\n                mask ="),
        ("    families = {name: {} for name in CONTRAST_FAMILIES}\n",
         "    families = {name: {} for name in CONTRAST_FAMILIES}\n    unavailable = {\"contrasts\": {}, \"whole_system\": {}}\n"),
        ("            key = f\"{cid}@{delta}\"\n            a, b = arms[left][delta], arms[right][delta]\n",
         "            key = f\"{cid}@{delta}\"\n"
         "            if delta not in arms[left] or delta not in arms[right]:\n"
         "                unavailable[\"contrasts\"][key] = {\"contrast\": cid, \"left\": left, \"right\": right,\n"
         "                                                 \"horizon_seconds\": delta, \"status\": \"not_available\",\n"
         "                                                 \"reason\": _D60_REASON}\n"
         "                continue\n"
         "            a, b = arms[left][delta], arms[right][delta]\n"),
        ("        for cid, (left, right) in (whole_system or {}).items():\n            key = f\"{cid}@{delta}\"\n",
         "        for cid, (left, right) in (whole_system or {}).items():\n            key = f\"{cid}@{delta}\"\n"
         "            if delta not in arms[left] or delta not in arms[right]:\n"
         "                unavailable[\"whole_system\"][key] = {\"contrast\": cid, \"left\": left, \"right\": right,\n"
         "                                                    \"horizon_seconds\": delta, \"status\": \"not_available\",\n"
         "                                                    \"reason\": _D60_REASON}\n"
         "                continue\n"),
        ("                    for cid in (\"C2\", \"C5\") if cid in contrasts}}\n",
         "                    for cid in (\"C2\", \"C5\") if cid in contrasts and delta in arms[contrasts[cid][0]]}}\n"),
        ("                            for name, by_delta in arms.items()}}\n",
         "                            for name, by_delta in arms.items() if delta in by_delta}}\n"),
        ("        adjusted = holm({k: v[\"p_value\"] for k, v in results.items()})\n",
         "        adjusted = _d60_holm({k: v[\"p_value\"] for k, v in results.items()}, _d60_pad(unavailable[\"contrasts\"]))\n"),
        ("report[family] = {\"contrasts\": results, \"holm_family_size\": len(results),",
         "report[family] = {\"contrasts\": results, \"holm_family_size\": len(results) + _d60_pad(unavailable[\"contrasts\"]),"),
        ("        adjusted = holm({k: v[\"p_value\"] for k, v in whole.items()})\n",
         "        adjusted = _d60_holm({k: v[\"p_value\"] for k, v in whole.items()}, _d60_pad(unavailable[\"whole_system\"]))\n"),
        ("\"contrasts\": whole, \"holm_family_size\": len(whole),",
         "\"contrasts\": whole, \"holm_family_size\": len(whole) + _d60_pad(unavailable[\"whole_system\"]),"),
        ("    return result\n",
         "    result[\"d60_only_deviation\"] = {\"arm\": \"frozen_sage_on\", \"evaluated_horizons\": [60],\n"
         "                                    \"not_available\": unavailable, \"holm_padded\": _D60_CFG[\"holm_pad\"],\n"
         "                                    \"holm_note\": \"registered Holm family sizes kept; unavailable contrasts are placeholders with p=1\" if _D60_CFG[\"holm_pad\"] else \"Holm over available contrasts only\"}\n"
         "    return result\n"),
    ],
    "evaluate_new_period": [
        ("                     for by_delta in arms.values() for per_event in by_delta[delta]}\n",
         "                     for by_delta in arms.values() if delta in by_delta for per_event in by_delta[delta]}\n"),
    ],
}

RUNNER_PATCHES = {
    "evaluate": [
        ("expected={x for by_horizon in derived.values() for ids in by_horizon.values() for x in ids}\n",
         "expected={x for by_horizon in derived.values() for ids in by_horizon.values() for x in ids}\n"
         " expected.update(primary._d60_excluded_ids(frozen))  # d60-only: frozen d30 cells are retained but not evaluated\n"),
    ],
}

# q57 change vs qwen/q56-frozen-d60/d60_only.py: the second FACTS_PATCHES entry (union 400 -> 395); found by running the facts script on an
# amended-freeze report ("Complete original retained identity union required").
FACTS_PATCHES = {
    "collect": [
        ("len(primary_ids) == 56 and sum(len(ids) for h in report['primary']['arms'].values() for ids in h.values()) == 56",
         "len(primary_ids) == 51 and sum(len(ids) for h in report['primary']['arms'].values() for ids in h.values()) == 51"),
        # q57: the retained-identity union check counts every retained id; the five frozen d30 cells (s0 failure + s1-s4 sealed arms) are
        # retained in the freeze but not evaluated, so the report carries 400 - 5 = 395 identities
        ("need(len(seen) == 400, 'Complete original retained identity union required')",
         "need(len(seen) == 395, 'Complete original retained identity union required')"),
    ],
}


RELEASE_HELPERS = '''
def _d60_padding(analysis, family):
    dev = analysis.get("d60_only_deviation") if isinstance(analysis, dict) else None
    if not isinstance(dev, dict) or dev.get("holm_padded") is not True:
        return 0
    return len(dev["not_available"]["whole_system" if family == "whole_system_ap" else "contrasts"])
'''

RELEASE_PATCHES = {
    "collect": [
        ('or family["holm_family_size"] != len(contrasts)):',
         'or family["holm_family_size"] != len(contrasts) + _d60_padding(analysis, name)):'),
    ],
}


def _patched(function, edits, filename):
    source = inspect.getsource(function)
    for anchor, replacement in edits:
        if source.count(anchor) != 1:
            raise RuntimeError(f"d60-only patch cannot be applied to {function.__name__}: anchor occurs "
                               f"{source.count(anchor)} times: {anchor!r}")
        source = source.replace(anchor, replacement)
    return compile(source, filename, "exec")


def _apply(module, patches, helpers=None):
    compiled = {}
    for name, edits in patches.items():
        compiled[name] = _patched(module.__dict__[name], edits, f"<d60_only:{name}>")
    helper_code = None if helpers is None else compile(helpers, "<d60_only:helpers>", "exec")
    if helper_code is not None:
        exec(helper_code, module.__dict__)
    for code in compiled.values():
        exec(code, module.__dict__)  # defines the function again under its own name, globals = module dict


def install(module=None, *, expected_sha256=PINNED_EVAL_SHA256):
    """Install the d60-only evaluation. Idempotent. Refuses a module file that is not the pinned one."""
    if module is None:
        from bgbench import forecast_custodian_eval as module
    if module.__dict__.get(MARK):
        return module
    digest = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise RuntimeError(f"d60-only: module source {digest} is not the pinned {expected_sha256}")
    _apply(module, PATCHES, HELPERS.replace("__HOLM_PAD__", repr(bool(HOLM_PAD))))
    module.__dict__[MARK] = True
    return module


def install_runner(runner_module):
    """Patch the R2 persistence runner's ``evaluate`` (needs ``install()`` to have run before the runner makes its private copy)."""
    if runner_module.__dict__.get(MARK):
        return runner_module
    _apply(runner_module, RUNNER_PATCHES)
    runner_module.__dict__[MARK] = True
    return runner_module


def install_report_facts(facts_module, release_module=None):
    """forecast_full_report_facts (51 primary identities) and, when given, forecast_release_facts (Holm family size
    = available contrasts + the declared placeholders). Install on the module objects the generator scripts import."""
    if release_module is not None and not release_module.__dict__.get(MARK):
        _apply(release_module, RELEASE_PATCHES, RELEASE_HELPERS)
        release_module.__dict__[MARK] = True
    if not facts_module.__dict__.get(MARK):
        _apply(facts_module, FACTS_PATCHES)
        facts_module.__dict__[MARK] = True
    return facts_module


def excluded_ids(custody_spec, module=None):
    if module is None:
        from bgbench import forecast_custodian_eval as module
    return module._d60_excluded_ids(custody_spec)
