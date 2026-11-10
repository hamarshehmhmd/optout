"""Watch vendor privacy/terms/data-use pages and tell you when they change."""
import datetime as _dt
import difflib
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.request

from . import __version__
from .util import state_dir

PAGES = [
    {"id": "anthropic-consumer-terms", "vendor": "Anthropic", "url": "https://www.anthropic.com/legal/consumer-terms"},
    {"id": "anthropic-privacy", "vendor": "Anthropic", "url": "https://www.anthropic.com/legal/privacy"},
    {"id": "claude-code-data-usage", "vendor": "Anthropic", "url": "https://code.claude.com/docs/en/data-usage"},
    {"id": "openai-privacy", "vendor": "OpenAI", "url": "https://openai.com/policies/privacy-policy/"},
    {"id": "openai-api-data-controls", "vendor": "OpenAI", "url": "https://developers.openai.com/api/docs/guides/your-data"},
    {"id": "gemini-apps-privacy-hub", "vendor": "Google", "url": "https://support.google.com/gemini/answer/13594961"},
    {"id": "github-privacy-statement", "vendor": "GitHub",
     "url": "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement"},
    {"id": "cursor-data-use", "vendor": "Cursor", "url": "https://cursor.com/data-use"},
    {"id": "cursor-privacy", "vendor": "Cursor", "url": "https://cursor.com/privacy"},
    {"id": "mistral-privacy", "vendor": "Mistral", "url": "https://legal.mistral.ai/terms/privacy-policy"},
]

_DROP = re.compile(r"<(script|style|noscript|svg|template|iframe|head)\b.*?</\1\s*>", re.S | re.I)
_CHROME = re.compile(r"<(nav|header|footer|aside)\b.*?</\1\s*>", re.S | re.I)
_BLOCK = re.compile(r"</?(p|div|li|ul|ol|h[1-6]|tr|td|th|br|section|article|main|table|dd|dt|blockquote)\b[^>]*>", re.I)


def extract_text(raw):
    """Readable text of an HTML page, one block per line, chrome removed."""
    s = _DROP.sub(" ", raw)
    m = re.search(r"<main\b[^>]*>(.*)</main\s*>", s, re.S | re.I) or re.search(r"<article\b[^>]*>(.*)</article\s*>", s, re.S | re.I)
    if m:
        s = m.group(1)
    else:
        b = re.search(r"<body\b[^>]*>(.*)</body\s*>", s, re.S | re.I)
        s = _CHROME.sub(" ", b.group(1) if b else s)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = _BLOCK.sub("\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    lines = []
    for ln in s.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if len(ln) >= 3:
            lines.append(ln)
    return "\n".join(lines) + "\n"


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"Mozilla/5.0 (compatible; optout/{__version__}; +https://github.com/hamarshehmhmd/optout)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
        "Accept-Language": "en-US,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - user-chosen URLs
        raw = r.read()
        charset = r.headers.get_content_charset() if hasattr(r, "headers") and r.headers else None
    text = raw.decode(charset or "utf-8", "replace")
    if url.endswith((".txt", ".md")) or not re.search(r"<(html|body|p|div)\b", text, re.I):
        return "\n".join(re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()) + "\n"
    out = extract_text(text)
    if len(out) < 200 and len(text) > 2000:  # odd markup (no <body>, unclosed tags): strip tags from everything
        out = extract_text("<body>" + re.sub(r"<(script|style)\b.*?</\1\s*>", " ", text, flags=re.S | re.I) + "</body>")
    return out


def _dir(home=None):
    return os.path.join(state_dir(home), "terms")


def load_pages(path=None):
    if not path:
        return PAGES
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["pages"] if isinstance(data, dict) else data


def check(pages, home=None, fetcher=fetch, now=None):
    d = _dir(home)
    os.makedirs(d, exist_ok=True)
    idx_path = os.path.join(d, "index.json")
    try:
        with open(idx_path, encoding="utf-8") as fh:
            index = json.load(fh)
    except (FileNotFoundError, ValueError):
        index = {}
    now = (now or _dt.datetime.now(_dt.timezone.utc)).replace(microsecond=0)
    results = []
    for pg in pages:
        pid, url = pg["id"], pg["url"]
        res = {"id": pid, "vendor": pg.get("vendor", ""), "url": url}
        try:
            text = fetcher(url)
        except urllib.error.HTTPError as e:
            res.update(status="error", detail=f"HTTP {e.code} (site may block automated fetches)")
            results.append(res)
            continue
        except Exception as e:  # noqa: BLE001
            res.update(status="error", detail=f"{type(e).__name__}: {e}"[:160])
            results.append(res)
            continue
        if len(text.strip()) < 200:
            res.update(status="error", detail=f"only {len(text.strip())} chars of text (blocked or JS-only page?)")
            results.append(res)
            continue
        sha = hashlib.sha256(text.encode()).hexdigest()
        txt_path = os.path.join(d, f"{pid}.txt")
        prev = index.get(pid)
        entry = dict(prev or {}, url=url, sha256=sha, checked=now.isoformat(), chars=len(text))
        if not prev or not os.path.exists(txt_path):
            res.update(status="new", detail=f"first snapshot, {len(text)} chars")
            entry["first_seen"] = now.isoformat()
        elif prev.get("sha256") == sha:
            res.update(status="same", detail=f"unchanged since {prev.get('changed', prev.get('first_seen', '?'))[:10]}")
        else:
            with open(txt_path, encoding="utf-8") as fh:
                old = fh.read()
            diff = list(difflib.unified_diff(old.splitlines(), text.splitlines(), f"{pid} (before)", f"{pid} (now)", n=1, lineterm=""))
            added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
            dpath = os.path.join(d, f"{pid}.{now.strftime('%Y%m%dT%H%M%SZ')}.diff")
            with open(dpath, "w", encoding="utf-8") as fh:
                fh.write("\n".join(diff) + "\n")
            entry["changed"] = now.isoformat()
            res.update(status="changed", detail=f"+{added} / -{removed} lines", diff=diff, diff_path=dpath)
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        index[pid] = entry
        results.append(res)
    with open(idx_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, sort_keys=True)
    return results
