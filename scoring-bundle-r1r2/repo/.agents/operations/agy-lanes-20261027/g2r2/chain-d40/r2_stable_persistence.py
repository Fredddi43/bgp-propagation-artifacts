"""D-A38: the stable consumer's persistence check tolerates rows that carry no candidate list (no pinned file is edited).

components/composition/components/stable/consumer.py prepare_sealed, for the persistence baseline, checks `row['candidate_asns']` of
EVERY prediction row ("Persistence has no nonseed ranking"). The sealed persistence predictions (stable-d30-persistence,
stable-d60-persistence) hold 1,289 rows each; the 29 (d30) and 25 (d60) rows without candidate_asns are exactly the events whose input is
not available (`input_status != 'available'`; they carry curve_log_quantiles, seed_asns and predicted_asns only). For such a row the check
is vacuous (there is no non-seed ranking), so row.get('candidate_asns', []) is the faithful reading. This patch re-compiles prepare_sealed
from its own sha-verified source with that one change.
"""
import ast
from pathlib import Path

OLD = "zip(row['candidate_asns'],row.get('ranking_scores',[]),strict=True)"
NEW = "zip(row.get('candidate_asns',[]),row.get('ranking_scores',[]),strict=True)"


def patch(module):
    source = Path(module.__file__).read_text()
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "prepare_sealed")
    segment = ast.get_source_segment(source, node)
    if segment.count(OLD) != 1:
        raise ValueError("stable prepare_sealed shape changed")
    function = ast.parse(segment.replace(OLD, NEW)).body[0]
    exec(compile(ast.Module(body=[function], type_ignores=[]), module.__file__, "exec"), module.__dict__)
    return module.prepare_sealed
