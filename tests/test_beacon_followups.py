import polars as pl

from bgbench.beacon_analysis import rov_meter


def test_rov_meter_ratio():
    vis = pl.DataFrame(
        {
            "prefix": [
                "93.175.146.0/24",
                "93.175.147.0/24",
                "84.205.83.0/24",
                "2001:7fb:fd02::/48",
                "2001:7fb:fd03::/48",
                "2001:7fb:ff03::/48",
            ],
            "sessions": [279, 49, 278, 271, 44, 272],
            "collectors": [20] * 6,
            "peer_asns": [200] * 6,
            "kind": [
                "rpki_valid",
                "rpki_invalid",
                "anchor",
                "rpki_valid",
                "rpki_invalid",
                "anchor",
            ],
            "setup": ["rpki", "rpki", "rrc03", "rpki", "rpki", "rrc03"],
            "family": [4, 4, 4, 6, 6, 6],
        }
    )
    m = rov_meter(vis)
    assert m["ipv4"]["rpki_unknown"] == 278 and m["ipv6"]["rpki_unknown"] == 272
    assert abs(m["ipv4"]["invalid_over_valid"] - 49 / 279) < 1e-3
    assert abs(m["ipv6"]["invalid_over_valid"] - 44 / 271) < 1e-3
