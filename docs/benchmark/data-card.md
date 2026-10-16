# Data card

| Item | Description |
|---|---|
| Period | January 2022 through August 2026 for event measurements; 2023–2025 for forecast comparisons; beacon snapshots extend through September 2026 |
| Replay collectors | RIPE RIS rrc25, rrc00, rrc12, rrc01, rrc03, rrc20, rrc15; RouteViews route-views3, route-views2, route-views.linx |
| Families | Origin changes, route leaks, withdrawal waves and recovery events |
| Labels | Sets of public AS numbers observed on relevant paths; horizons and temporal splits are stored per event |
| RPKI | Daily archived ROAs determine new-origin and previous-origin validity |
| ROV | Latest available RoVista observation at or before the event; missing history remains unknown; coverage and frozen-series variants are reported |
| Selection | Stratified and catalogue-anchored events plus a separate label-free invalid stratum |
| Error rows | Retained for provenance; exclude non-null errors from analyses |
| Raw inputs | Not redistributed |

## Interpretation and limitations

The affected AS sets describe paths visible at collectors. They do not establish every intermediate AS's selected route, forwarding state or complete Internet reach. Catalogues have different coverage by year and do not supply ground truth for every event. A RPKI-invalid announcement alone does not identify malicious behavior. See `label-limits.md` for detector limitations and known archive gaps. That document records the original three-year benchmark; the release extends the measurement tables to 2022 and partial 2026.

Event selection is retrospective, including an analysis-window origin-change
whitelist. The 2024 discovery inventory additionally includes wider RIS
beacon-week observations; replay always uses the ten collectors above. This
forecast benchmark evaluates early prediction for selected events, not an online
event-discovery system.

The primary outward/return comparison uses each session's first qualifying post-identifier origin transition in both directions. Its retained state resets daily and omits withdrawals. Pair links share unique event payloads, and confidence intervals resample connected groups of shared events. These conditional path observations do not measure outage duration. The PCH comparison is restricted to verified same-day windows and available archive feeds.

Withdrawal path loss requires a latest-prior baseline RIB no more than seven days old at every replay collector. The retained archives support 50 events in 2024 and six in 2025; all six 2025 events belong to the training split. The other 245 selected candidates retain explicit unavailable labels rather than zero footprints. The released baseline revision and source audit make these exclusions independently checkable.

Membership scores use the full observed target, including misses outside model candidate graphs. Candidate-only ranking scores are identified separately. Within-year and forward cross-year forecasts exclude training labels whose observation windows have not finished by the first test onset. The pooled-year split is retrospective; it is not a prospective deployment simulation.

Origin-change and leak membership stops at the first occurrence of the event's
actor on each observed path. A suffix beyond a repeated actor does not add
affected ASes. Graph seeds and targets use the same canonical membership as the
measurement tables.

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

No raw catalogue responses, raw topology files, raw ROAs or foundation-model base weights are included. Graph checkpoints and prefix models are the study's trained states. The Chronos adapter requires the base-model revision named in its reproduction metadata. The release does not include full training graph tensors or optimizer checkpoints.
