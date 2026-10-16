from datetime import UTC, datetime

from bgbench.beacons import (
    BEACON_PREFIXES,
    SCHEDULED_PREFIXES,
    announce_slot_for,
    decode_aggregator,
    registry,
    withdraw_slot_for,
)


def test_registry_counts():
    r = registry()
    assert len(BEACON_PREFIXES) == len(r)  # no duplicate prefixes
    assert "84.205.64.0/24" in SCHEDULED_PREFIXES and "84.205.80.0/24" not in SCHEDULED_PREFIXES
    assert sum(b.kind == "anchor" for b in r) == 26 + 12  # 23 v6 + 3 v4 per-RRC, 12 anycast


def test_decode_aggregator_roundtrip():
    # 2024-06-15 08:00:00 UTC = 14 days * 86400 + 8*3600 = 1238400 s since month start
    secs = 14 * 86400 + 8 * 3600
    ip = f"10.{(secs >> 16) & 255}.{(secs >> 8) & 255}.{secs & 255}"
    seen = datetime(2024, 6, 15, 8, 0, 3, tzinfo=UTC)
    orig, field = decode_aggregator(64512 + 17, ip, seen)
    assert orig == datetime(2024, 6, 15, 8, 0, 0, tzinfo=UTC)
    assert field == 17
    assert decode_aggregator(3356, "10.0.0.1", seen) == (None, None)
    assert decode_aggregator(64512, "192.0.2.1", seen) == (None, None)


def test_month_boundary_straddle():
    # announced 23:59:58 on May 31, seen 00:00:04 June 1 -> counter is May-relative
    secs = 30 * 86400 + 23 * 3600 + 59 * 60 + 58
    ip = f"10.{(secs >> 16) & 255}.{(secs >> 8) & 255}.{secs & 255}"
    seen = datetime(2024, 6, 1, 0, 0, 4, tzinfo=UTC)
    orig, _ = decode_aggregator(64512, ip, seen)
    assert orig == datetime(2024, 5, 31, 23, 59, 58, tzinfo=UTC)


def test_slots():
    ts = datetime(2024, 6, 15, 13, 47, tzinfo=UTC)
    assert announce_slot_for(ts, "beacon") == datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    assert announce_slot_for(ts, "fast") == datetime(2024, 6, 15, 13, 40, tzinfo=UTC)


def test_withdraw_slots():
    # 00:00:05: withdraw phase still the 22:00 one from the previous day's last cycle
    assert withdraw_slot_for(datetime(2024, 6, 15, 0, 0, 5, tzinfo=UTC), "beacon") == datetime(
        2024, 6, 14, 22, 0, tzinfo=UTC
    )
    assert withdraw_slot_for(datetime(2024, 6, 15, 2, 1, 0, tzinfo=UTC), "beacon") == datetime(
        2024, 6, 15, 2, 0, tzinfo=UTC
    )
    assert withdraw_slot_for(datetime(2024, 6, 15, 3, 59, 0, tzinfo=UTC), "beacon") == datetime(
        2024, 6, 15, 2, 0, tzinfo=UTC
    )
    assert withdraw_slot_for(datetime(2024, 6, 15, 13, 5, 0, tzinfo=UTC), "fast") == datetime(
        2024, 6, 15, 12, 50, tzinfo=UTC
    )
    assert withdraw_slot_for(datetime(2024, 6, 15, 13, 31, 0, tzinfo=UTC), "fast") == datetime(
        2024, 6, 15, 13, 30, tzinfo=UTC
    )
