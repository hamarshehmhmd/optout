from optout.util import dig, load_jsonc, mini_toml, strip_jsonc, truthy


def test_strip_jsonc_keeps_strings():
    t = '{ // c\n "a": "http://x//y", /* b */ "b": [1,2,],\n}'
    import json
    assert json.loads(strip_jsonc(t)) == {"a": "http://x//y", "b": [1, 2]}


def test_load_jsonc_missing_and_empty(tmp_path):
    assert load_jsonc(str(tmp_path / "nope.json")) == (None, None)
    p = tmp_path / "e.json"
    p.write_text("  ")
    assert load_jsonc(str(p)) == ({}, None)
    p.write_text("{bad")
    d, err = load_jsonc(str(p))
    assert d is None and "cannot parse" in err


def test_mini_toml_tables_and_dotted():
    d = mini_toml('model = "x"\nanalytics.enabled = false\n[feedback]\nenabled = true # c\n[history]\npersistence = \'none\'\nmax_bytes = 10\n')
    assert dig(d, "analytics.enabled") is False
    assert dig(d, "feedback.enabled") is True
    assert dig(d, "history.persistence") == "none"
    assert dig(d, "history.max_bytes") == 10


def test_truthy():
    assert truthy("1") and truthy("true") and truthy(True)
    assert not truthy("0") and not truthy("") and not truthy(None) and not truthy("false")
