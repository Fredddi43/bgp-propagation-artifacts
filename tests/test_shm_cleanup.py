"""release_shm removes the whole bgbench-<id> tree once the last scratch dir in it is gone."""

from pathlib import Path

from bgbench import config


def _shm(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BGBENCH_SHM", str(tmp_path))
    monkeypatch.setenv("SLURM_JOB_ID", "4242")
    return config.shm_dir()


def test_last_scratch_removes_job_dir(tmp_path, monkeypatch):
    root = _shm(tmp_path, monkeypatch)
    day = root / "xday" / "rrc00" / "2023-01-05"
    (day / "pq").mkdir(parents=True)
    (day / "pq" / "part-00.parquet").write_bytes(b"x")
    config.release_shm(day)
    assert not root.exists()
    assert tmp_path.exists()


def test_sibling_scratch_is_kept(tmp_path, monkeypatch):
    root = _shm(tmp_path, monkeypatch)
    a = root / "xday" / "rrc00" / "2023-01-05"
    b = root / "xday" / "rrc01" / "2023-01-05"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    config.release_shm(a)
    assert not (root / "xday" / "rrc00").exists()
    assert b.exists()
    config.release_shm(b)
    assert not root.exists()


def test_path_outside_shm_leaves_parents(tmp_path, monkeypatch):
    _shm(tmp_path / "shm", monkeypatch)
    other = tmp_path / "elsewhere" / "x"
    other.mkdir(parents=True)
    config.release_shm(other)
    assert not other.exists()
    assert (tmp_path / "elsewhere").exists()
