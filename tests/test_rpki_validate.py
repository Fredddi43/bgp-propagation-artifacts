from bgbench.rpki_validate import validity


def test_covering_too_short_maxlength_is_invalid():
    roas = {"10.0.0.0/16": [(16, 42)]}
    assert validity("10.0.0.0/24", 42, roas) == ("invalid", 1, "invalid_length")
    assert validity("10.0.0.0/24", 43, roas) == ("invalid", 1, "invalid_asn")


def test_any_match_wins_and_all_covering_roas_count():
    roas = {"10.0.0.0/16": [(16, 42), (24, 42), (24, 43)]}
    assert validity("10.0.0.0/24", 42, roas) == ("valid", 3, "")


def test_default_roa_and_as_zero():
    assert validity("10.0.0.0/24", 42, {"0.0.0.0/0": [(32, 42)]}) == ("valid", 1, "")
    assert validity("2001:db8::/32", 42, {"::/0": [(128, 42)]}) == ("valid", 1, "")
    assert validity("10.0.0.0/24", 0, {"10.0.0.0/24": [(24, 0)]}) == ("invalid", 1, "invalid_asn")
    assert validity("10.0.0.0/24", 42, {}) == ("unknown", 0, "")
