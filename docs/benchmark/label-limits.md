# Limits of the self-supervised labels (benchmark documentation, ADR-0019)

Every event in the benchmark is *found* and *labelled* without human ground truth. Each mechanism has known blind
spots, measured on 2024 where possible. Users of the benchmark should read this before comparing methods.

## Event discovery

| family | mechanism | known limits (measured) |
|---|---|---|
| origin change (hijack-type) | identifier v2: per-(peer, prefix) origin change agreeing at ≥ 2 collectors in a 5-min bin, flapper whitelist | recall vs Cloudflare hijacks ≥ 10 peers 0.66–0.73 per month; blind to events seen by < 10 of Cloudflare's peers; ~100× null |
| leak (novelty) | identifier v4: first-seen path triple (x, a, b) in the month, valley-free violation vs CAIDA | 17–22 % of Cloudflare leaks hit (8.5–10 % with a violation); **95 % of the leaks are carried at our collectors** — the miss is that the leaked paths reuse adjacencies already seen that month |
| leak (prefix-level) | identifier v5: (x, a, b, prefix) on a violating triple, first seen that day | inherits CAIDA relationship errors: the documented 2024-06-27 Cloudflare leak (AS262504 → AS1031) is classified provider→customer by CAIDA serial-1 and therefore invisible to it |
| withdrawal wave | identifier v1 on per-minute withdrawals, robust z ≥ 8, ≥ 3 collectors, ≥ 2 consecutive minutes | no external labels; 50 candidates in 2024, 1–4 min long; top-of-hour artefacts checked (2 of 50) |

## Label coverage by year
- Cloudflare Radar hijack events: available for 2023–2025 (23.5 k rows in 2023).
- **Cloudflare Radar leak events: none returned for 2023** (the leak feed starts in 2024); leak-detector recall is
  therefore reported for 2024 and 2025 only, and 2023 leak events are unlabelled in the inventory.
- Cloudflare Radar leak events carry no prefixes (public API, verified with a full-access token 2026-09-09). For the
  1,403 Radar leaks that match a replayed 2024 leak event (same leaker, t₀ within ±10 min) we reconstruct the leaked
  prefix set from our own replay: our count equals Radar's `prefix_count` for 81 % (1,136) and is ≥ it for 92 %; the
  ratio ours/Radar is 1.0 at p10 and p50, 1.33 at p90 (median count 1 in both). Table:
  `labels/2024-01-01_2025-01-01/cloudflare_leaks_prefixes_reconstructed.parquet` (`scripts/label_leak_prefixes.py`). 2025: Radar's
  leak feed is 6.7× larger (104,111 events); 10,868 match a replayed event, count agreement 80 % exact / 93 % ≥ (ratio p90 1.67).
- GRIP: 420 k events in 2023 with three days skipped after repeated server errors (2023-05-15, 07-12, 07-20); per-day
  skips are recorded in each labels run's summary.

## Onset (t₀)
- t₀ is the first observation of the anomalous route at any of the 10 collectors (ADR-0018). For origin-change events
  the identifier's 5-min bin lagged it by up to tens of minutes for 10 % of events; the replay recomputes it.
- Novelty resets at month boundaries: leak events dated the 1st at 00:00 (e.g. `20240201T000000_leak_3356`) are not
  onsets. 10 % of leak events have a first observation ≥ 1 h before t₀ for this or the "old upstream" reason; the
  benchmark reports leak floors on the clean subset (first observation within 60 s of t₀) and marks the rest.

## Extent labels (membership)
- Path membership: ASes on anomalous paths collector-side of the actor (origin for hijacks, leaker for leaks). ASes
  beyond the actor are the legitimate upstream and are not counted. Ten vantage points see a fraction of the Internet;
  extent is a lower bound and biased towards the collectors' neighbourhoods (top-10 VP selection, ADR-0014).
- Leak membership counts only paths through the *novel* upstream triple (x, leaker, source); paths via the leaker's
  old upstreams are baseline.
- Path-loss membership (withdrawal waves) needs the weekly RIBs and is defined but not yet run at scale.

## Data integrity
- Nine hourly Parquet parts of the kept beacon week (rrc20/rrc25, hour 23, several days) were truncated (no footer) and
  were re-ingested on 2026-09-06; beacon-week analyses before that date miss those hours.
- Archive gaps: route-views.linx 2023-10-20..23 have no files at the source; recorded as empty manifests.
- Transient download failures (RIPE throttling above ~120 concurrent jobs, RouteViews disconnects at 120) fail the job
  and are retried; a manifest is only written for a complete day.

- 2023 origin-change replay: rrc03 on 2023-02-09 (a withdrawal storm day) could not be replayed within 128 GB after three attempts,
  and RouteViews-LINX 2023-10-20…23 have no archive files; events on those days carry 9 of 10 collectors (marked in each event's
  `collectors_with_parts`).

## Vantage points
rrc25, rrc00, rrc12, rrc01, route-views3, rrc03, route-views2, rrc20, rrc15, route-views.linx (ADR-0014 heuristic over
BGPKit peer stats; 235 full-feed peer ASNs). Cloudflare Radar sees ~1,700 peers; label recall by Cloudflare peer count
(1–9 / 10–49 / 50+) is reported wherever labels are used.
