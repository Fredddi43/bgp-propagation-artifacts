"""Wiring of the amended retention spec (frozen-2025 reference at d60 only) into the G3/R2 chain.

ONE implementation: d60_only.py (copy of qwen/q56-frozen-d60/d60_only.py; source-patched copies of the pinned evaluator functions,
runner `evaluate` and report-facts `collect`; no pinned file is edited). This module only decides WHEN it is engaged and gives the
chain scripts a single entry point. Engaged exactly when the freeze lists a frozen_sage_on 30 s cell in `retained_failures`
(the amended spec); a full freeze never engages it and every chain script then behaves exactly as before.
"""
import importlib.util

import d60_only


def _is_frozen_d30(role):
    """Role of the evaluator arm frozen_sage_on (forecast_custodian_eval.role_arm, :269-276) at 30 s. Spelled out so r2_exec needs no
    bgbench import; d60_only.install's own check (require_failure_record, via the pinned role_arm) re-verifies it on the real module."""
    return (isinstance(role, dict) and role.get("family") == "neural" and role.get("variant") == "core"
            and role.get("panel") == "reference" and role.get("training") == "frozen_2025" and role.get("message_passing") == "sage"
            and role.get("history") == "on" and role.get("horizon_seconds") == 30)


def is_amended(freeze, ev=None):
    """True iff a frozen_sage_on d30 role is a retained failure (the amended freeze). Decided from the freeze content alone."""
    return any(_is_frozen_d30(a.get("role")) for a in freeze.get("retained_failures") or [] if isinstance(a, dict))


def fresh_installed(ev):
    """An INDEPENDENT module object of the pinned evaluator file with the d60-only patches installed. sys.modules is not touched,
    so a full-freeze evaluation in the same process is unaffected. d60_only.install itself refuses a file that is not the pinned one."""
    spec = importlib.util.spec_from_file_location("bgbench.forecast_custodian_eval_d60", ev.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return d60_only.install(module)


def evaluator_for(ev, freeze):
    """The evaluator module to derive/evaluate with: `ev` unchanged for a full freeze, a d60-only copy for the amended one."""
    return fresh_installed(ev) if is_amended(freeze, ev) else ev


def unevaluated_ids(freeze, ev):
    """Arm ids retained in the freeze but left out of the evaluation (frozen d30 cells: executable s1.. and the failed s0). [] if full."""
    if not is_amended(freeze, ev):
        return []
    return sorted(d60_only.excluded_ids(freeze, fresh_installed(ev)))


def engage_runner(runner_module, freeze_bytes_or_doc):
    """r2_exec: called on the exec'd pinned runner module BEFORE module.run. Wraps its `scientific_modules` so the evaluator module
    the runner itself loads (staged source, sys.modules) is d60-patched before anything copies it (runner.py:213 private_primary),
    and patches the runner's `evaluate` partition anchor (runner.py:229). Returns True when engaged."""
    import json
    freeze = json.loads(freeze_bytes_or_doc) if isinstance(freeze_bytes_or_doc, (bytes, str)) else freeze_bytes_or_doc
    if not is_amended(freeze):
        return False
    d60_only.install_runner(runner_module)
    original = runner_module.scientific_modules

    def scientific_modules(plan):
        evaluator, custody = original(plan)
        d60_only.install(evaluator)
        return evaluator, custody

    runner_module.scientific_modules = scientific_modules
    return True
