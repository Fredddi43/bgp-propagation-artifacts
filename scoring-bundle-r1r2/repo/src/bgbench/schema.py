"""Parquet schema for parsed BGP update elements. One row per element (announce/withdraw per prefix)."""

from __future__ import annotations

import pyarrow as pa

FIELDS = [  # order matters: matches iter_tuple_batches(FIELDS)
    "timestamp",
    "elem_type",
    "peer_ip",
    "peer_asn",
    "prefix",
    "as_path",
    "origin_asns",
    "next_hop",
    "communities",
    "aggr_asn",
    "aggr_ip",
]

ARROW_SCHEMA = pa.schema(
    [
        pa.field("ts", pa.timestamp("us", tz="UTC")),
        pa.field("elem_type", pa.dictionary(pa.int8(), pa.string())),  # "A" / "W"
        # large_string everywhere: a single busy hour on a big collector exceeds 2 GB of string offsets when
        # concatenated + sorted (ArrowInvalid: offset overflow). Parquet stores both identically.
        pa.field("peer_ip", pa.large_string()),
        pa.field("peer_asn", pa.uint32()),
        pa.field("prefix", pa.large_string()),
        pa.field("as_path", pa.large_string()),  # space-separated, sets in braces
        pa.field("origin_asn", pa.uint32()),  # first origin; None for W / sets
        pa.field("origin_asns", pa.list_(pa.uint32())),
        pa.field("next_hop", pa.large_string()),
        pa.field("communities", pa.list_(pa.large_string())),
        pa.field("aggr_asn", pa.uint32()),
        pa.field("aggr_ip", pa.large_string()),
        pa.field("collector", pa.dictionary(pa.int16(), pa.string())),
    ]
)
