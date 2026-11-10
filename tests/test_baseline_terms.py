import json
import os

import make_demo_home
from optout import baseline, checks, terms


def run(home):
    return checks.scan(checks.Ctx(home=home, env={}, cwd=home, plat="linux"))


def test_drift_detects_cursor_storage_downgrade(demo_home):
    baseline.save(run(demo_home), demo_home)
    make_demo_home.cursor_db(demo_home, "PRIVACY_MODE_NO_TRAINING")
    diffs = baseline.compare(baseline.load(demo_home), run(demo_home))
    kinds = {(k, i) for k, i, *_ in diffs}
    assert ("weaker", "cursor.privacy-mode") in kinds


def test_drift_detects_reenabled_setting_and_improvement(demo_home):
    p = os.path.join(demo_home, ".claude", "settings.json")
    baseline.save(run(demo_home), demo_home)
    d = json.load(open(p))
    d["env"] = {"DISABLE_TELEMETRY": "1"}  # telemetry off, error reports back on
    json.dump(d, open(p, "w"))
    diffs = {i: k for k, i, *_ in baseline.compare(baseline.load(demo_home), run(demo_home))}
    assert diffs["claude.error-reports"] == "weaker"
    assert diffs["claude.telemetry"] == "better"


def test_no_drift(demo_home):
    baseline.save(run(demo_home), demo_home)
    assert baseline.compare(baseline.load(demo_home), run(demo_home)) == []


HTML1 = "<html><head><title>t</title><script>var x=1</script></head><body><nav>Menu</nav><main><h1>Privacy</h1><p>We do not train on your data.</p>" + "<p>Filler paragraph number %d about data.</p>" * 12 + "</main><footer>(c)</footer></body></html>"


def test_extract_text_drops_chrome():
    t = terms.extract_text(HTML1 % tuple(range(12)))
    assert "We do not train on your data." in t
    assert "Menu" not in t and "var x" not in t and "(c)" not in t


def test_terms_new_same_changed_error(tmp_path):
    pages = [{"id": "p", "vendor": "V", "url": "https://example.test/p"}, {"id": "q", "url": "https://example.test/q"}]
    content = {"https://example.test/p": HTML1 % tuple(range(12))}

    def fetcher(url):
        if url not in content:
            raise OSError("boom")
        return terms.extract_text(content[url])

    home = str(tmp_path)
    r = {x["id"]: x for x in terms.check(pages, home, fetcher)}
    assert r["p"]["status"] == "new" and r["q"]["status"] == "error"
    r = {x["id"]: x for x in terms.check(pages, home, fetcher)}
    assert r["p"]["status"] == "same"
    content["https://example.test/p"] = content["https://example.test/p"].replace("do not train", "may train")
    r = {x["id"]: x for x in terms.check(pages, home, fetcher)}
    assert r["p"]["status"] == "changed"
    assert any(l.startswith("+") and "may train" in l for l in r["p"]["diff"])
    assert os.path.exists(r["p"]["diff_path"])


def test_terms_rejects_tiny_pages(tmp_path):
    r = terms.check([{"id": "x", "url": "u"}], str(tmp_path), lambda u: "Just a moment...\n")
    assert r[0]["status"] == "error" and "chars" in r[0]["detail"]


def test_terms_file_url(tmp_path):
    f = tmp_path / "page.html"
    f.write_text(HTML1 % tuple(range(12)))
    r = terms.check([{"id": "local", "url": f.as_uri()}], str(tmp_path / "st"))
    assert r[0]["status"] == "new"


def test_builtin_pages_are_unique():
    ids = [p["id"] for p in terms.PAGES]
    assert len(ids) == len(set(ids)) and all(p["url"].startswith("https://") for p in terms.PAGES)
