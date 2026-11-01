"""D-A28 (R2 side): orjson for the very large prediction payloads only.

forecast_custodian_eval.evaluate_new_period does json.loads(<sealed predictions bytes>) for each arm; the origin valid arms are ~18 GB
each, ~8 min per arm with the stdlib parser. orjson parses the same JSON ~3-4x faster and returns the same Python values (checked ==
on real prediction files, see the deviations ledger). The proxy only intercepts json.loads of a single bytes argument larger than
MIN_BYTES; any orjson error falls back to the stdlib parser, and every other json attribute is the stdlib's.
"""
import json

MIN_BYTES = 64 << 20


class JsonProxy:
    def __getattr__(self, name):
        return getattr(json, name)

    def loads(self, s, *args, **kwargs):
        if not args and not kwargs and isinstance(s, (bytes, bytearray)) and len(s) > MIN_BYTES:
            try:
                import orjson
                return orjson.loads(s)
            except Exception:
                pass
        return json.loads(s, *args, **kwargs)


def install(evaluator):
    evaluator.json = JsonProxy()
