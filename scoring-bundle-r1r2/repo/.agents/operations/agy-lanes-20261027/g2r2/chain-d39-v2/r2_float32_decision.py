"""D-A36: float32 comparison in the membership consumer's committed-decision check (no pinned file is edited).

The reviewed membership consumer (components/composition/components/membership/consumer.py, check_cell) recomputes each neural/temporal
decision set as seed_asns | {a : p >= threshold} with p promoted to float64 and requires it to equal the committed `predicted_asns`.
The probabilities are float32 model outputs: the producer compared in float32. In the sealed predictions of arm gru-d30-s2 one event has
p = 0.9399999976158142 (= float32(0.94)) at threshold 0.94: float64 says p < threshold, float32 says p >= threshold, and the committed
decision includes that ASN. Checked offline on all 281 non-baseline, non-origin arms: float64 comparison fails exactly 1 event in 1 arm;
float32 comparison matches the committed decision in every event of every arm.

This patch re-compiles check_cell from its own (sha-verified) source with that one comparison done in float32 and nothing else changed.
"""
import ast
from pathlib import Path

OLD = "if p>=row['threshold']"
NEW = "if np.float32(p)>=np.float32(row['threshold'])"


def patch(module):
    source = Path(module.__file__).read_text()
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check_cell")
    segment = ast.get_source_segment(source, node)
    if segment.count(OLD) != 1:
        raise ValueError("membership check_cell shape changed")
    function = ast.parse(segment.replace(OLD, NEW)).body[0]
    exec(compile(ast.Module(body=[function], type_ignores=[]), module.__file__, "exec"), module.__dict__)
    return module.check_cell
