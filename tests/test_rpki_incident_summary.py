import importlib.util
from pathlib import Path

import polars as pl

spec=importlib.util.spec_from_file_location("rpki_summary",Path(__file__).parents[1]/"scripts/rpki_validity_events.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_incident_test_floor_excludes_training_rows_with_same_incident():
    events=pl.DataFrame({"validity":["invalid"]*4,"incident":["a","a","b","c"],
        "split":["train","test","test","train"],"j30":[0.,1.,.5,0.],
        "asns_final_2h":[10,20,30,40],"growing30":[True,False,True,True]})
    result=module.incident_summary(events)["invalid"]
    assert result["persist_j30_incident_mean"]==.75
    assert result["incidents"]==3 and result["events"]==4
    assert result["test_incidents"]==2 and result["mixed_split_incidents"]==1
    assert result["reach_p50_of_incident_medians"]==30
