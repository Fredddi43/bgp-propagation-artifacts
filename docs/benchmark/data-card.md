# Data card

| Item | Description |
|---|---|
| Period | January 2022 through August 2026 for measurements; 2023–2025 for forecast comparisons |
| Collectors | RIPE RIS rrc25, rrc00, rrc12, rrc01, rrc03, rrc20, rrc15; RouteViews route-views3, route-views2, route-views.linx |
| Families | Origin changes, route leaks, withdrawal waves and recovery events |
| Labels | Sets of public AS numbers observed on relevant paths; horizons and temporal splits are stored per event |
| RPKI | Daily archived ROAs determine new-origin and previous-origin validity |
| ROV | Derived RoVista/frontier summaries, including frozen-series sensitivity variants |
| Selection | Stratified and catalogue-anchored events plus a separate label-free invalid stratum |
| Error rows | Retained for provenance; exclude non-null errors from analyses |
| Raw inputs | Not redistributed |

## Interpretation and limitations

The affected AS sets are collector-visible lower bounds, not complete Internet reach. Catalogues have different coverage by year and do not supply ground truth for every event. A RPKI-invalid announcement alone does not identify malicious behavior. See `label-limits.md` for detector limitations and known archive gaps. That document records the original three-year benchmark; the release extends the measurement tables to 2022 and partial 2026.

Scientific identifiers, prefix addresses, event times, AS numbers and collector names remain intact. Author names, institutional contacts, private host paths, credentials, original git history and operational logs are excluded. The release includes derived measurement tables, not private route-server dumps or personal traffic data.

## Sources and terms

The code is provided under the MIT license in the repository root. This license does not relicense third-party data or pretrained models. Derived measurements retain any applicable upstream conditions and citation obligations. Obtain raw inputs from their original providers under those providers' terms:

- RIPE RIS: <https://data.ris.ripe.net/>
- RouteViews: <https://archive.routeviews.org/>
- PCH public routing archives: <https://downloads.pch.net/files/BGP_Routing_Data/>
- CAIDA AS relationships: <https://publicdata.caida.org/datasets/as-relationships/>
- RIPE RPKI archive: <https://ftp.ripe.net/rpki/>
- RoVista: <https://api.rovista.netsecurelab.org/>
- Cloudflare Radar: <https://radar.cloudflare.com/routing>
- GRIP: <https://grip.inetintel.cc.gatech.edu/>

No raw catalogue responses, raw topology files, raw ROAs or foundation-model weights are included. Graph checkpoints are the study's retained trained model states. They do not include the full training graph tensors.
