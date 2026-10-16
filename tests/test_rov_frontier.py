"""Historical availability must be applied at each event date, before aggregation."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import polars as pl


def test_frontier_cached_dates_preserve_naive_historical_measurements(tmp_path):
    for folder in ("rpki/rovista", "eventset/2024", "graphs"):
        (tmp_path / folder).mkdir(parents=True)
    measurements = [(1,"2023-12-31",.1), (1,"2024-01-03",.9), (2,"2024-01-02",.7),
                    (3,"2023-12-31",.8), (4,"2024-02-01",1.), (5,"2023-12-31",0.)]
    pl.DataFrame(measurements, schema=["asn","date","ratio"], orient="row").write_parquet(tmp_path / "rpki/rovista/as_rov_series.parquet")
    edges = [(1,2),(2,3),(3,4),(4,5),(5,1)]
    pl.DataFrame(edges, schema=["u","v"], orient="row").write_parquet(tmp_path / "graphs/20240101.rel.parquet")
    events = [{"event_id":f"202401{1+i//10:02d}T00{i%10:02d}00_event", "error":None,"split":"test",
               "set_final_2h":[i%5+1],"asns_final_2h":1,"reason":"catalogue"} for i in range(40)]
    pl.DataFrame(events).write_parquet(tmp_path / "eventset/2024/events.parquet")
    pl.DataFrame({"event_id":[x["event_id"] for x in events],"validity":["invalid"]*40}).write_parquet(tmp_path / "eventset/2024/rpki_validity.parquet")
    script = Path(__file__).resolve().parents[1] / "scripts/rov_frontier.py"
    subprocess.run([sys.executable,str(script),"2024"], env={**os.environ,"BGBENCH_DATA_ROOT":str(tmp_path)}, check=True, capture_output=True)
    rows = pl.read_parquet(tmp_path / "eventset/2024/rov_frontier.parquet")
    expected_odds = []
    for event, row in zip(events, rows.iter_rows(named=True)):
        day = event["event_id"][:4]+"-"+event["event_id"][4:6]+"-"+event["event_id"][6:8]
        carriers = set(event["set_final_2h"])
        frontier = {v for u,v in edges if u in carriers} | {u for u,v in edges if v in carriers}
        frontier -= carriers
        counts = []
        for label, asns in (("carriers", carriers), ("frontier", frontier)):
            measured = []
            for asn in asns:
                history = sorted((date,ratio) for a,date,ratio in measurements if a==asn and date<=day)
                if history: measured.append(history[-1][1])
            enforcing = sum(value>=.5 for value in measured)
            assert row[label+"_measured"] == len(measured)
            assert row[label+"_enforcing"] == enforcing
            counts.append((len(measured),enforcing))
        if counts[0][0] and counts[1][0]:
            pc,pf = [(n+.5)/(total+1) for total,n in counts]
            odds = math.log((pf/(1-pf))/(pc/(1-pc)))
            assert abs(row["log_odds"]-odds)<1e-12
            expected_odds.append(odds)
        else:
            assert row["log_odds"] is None
    saved = json.loads((tmp_path / "eventset/2024/rov_frontier.json").read_text())["by_validity"]["invalid"]
    assert saved["events_with_both_measured"] == len(expected_odds)
    assert saved["log_odds_frontier_vs_carriers_mean"] == round(float(np.mean(expected_odds)),3)
    rng = np.random.default_rng(0)
    interval = np.percentile([np.mean(rng.choice(expected_odds,len(expected_odds))) for _ in range(1000)],[2.5,97.5])
    assert saved["log_odds_mean_ci95_bootstrap"] == [round(float(x),3) for x in interval]
