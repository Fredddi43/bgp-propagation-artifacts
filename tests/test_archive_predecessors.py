import gzip
import importlib.util
from pathlib import Path
import struct
import pytest
spec=importlib.util.spec_from_file_location('predecessors',Path(__file__).parents[1]/'scripts/audit_archive_predecessors.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_mrt_prefilter_preserves_extended_timestamp_bytes(tmp_path):
    def row(seconds,micro):
        payload=struct.pack('!I',micro)+b'payload'
        return struct.pack('!IHHI',seconds,17,1,len(payload))+payload
    before=row(99,999999);edge=row(100,159732);after=row(101,0)
    source=tmp_path/'raw.gz';source.write_bytes(gzip.compress(before+edge+after))
    dest=tmp_path/'selected.mrt';report=m.retain_mrt_since(source,dest,100)
    assert dest.read_bytes()==edge+after
    assert report['mrt_records']==3 and report['retained_mrt_records']==2
    source.write_bytes(gzip.compress(before+edge[:-1]))
    with pytest.raises(ValueError,match='truncated MRT payload'):m.retain_mrt_since(source,dest,100)


def test_predecessor_url_month_rollover():
    assert m.predecessor_url('http://archive.routeviews.org/route-views3/bgpdata/2022.05/UPDATES/updates.20220501.0000.bz2',1651358700).endswith('/2022.04/UPDATES/updates.20220430.2245.bz2')
