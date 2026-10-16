"""Smoke test: parse BGPKit's public example update file end-to-end (network required)."""

from pathlib import Path

from bgbench.parse import parse_file


def test_parse_example(tmp_path: Path):
    tbl, n = parse_file("https://spaces.bgpkit.org/parser/update-example", "test")
    assert n > 0
    assert tbl.num_rows == n
    assert set(tbl.column("elem_type").to_pylist()) <= {"A", "W"}
    assert tbl.schema.field("ts").type.unit == "us"
