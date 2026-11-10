"""Account-side data controls that live on vendor servers, not on disk.

optout cannot read these without your browser session, so it keeps a dated
ledger of when you last looked ("attestations") and tells you when that check
is stale. Every entry cites where the setting lives."""
import datetime as _dt
import json
import os

from .util import state_dir

ACCOUNTS = {
    "chatgpt": {
        "product": "ChatGPT / Codex (signed in with ChatGPT)",
        "setting": "Settings > Data controls > \"Improve the model for everyone\"",
        "off_means": "Off",
        "url": "https://chatgpt.com/#settings/DataControls",
        "applies": "Free, Plus and Pro accounts. Business/Enterprise/Edu workspaces are not trained on by default.",
        "why": "Reported silently re-enabled on Codex chats (HN 50352757, Nov 3 2026; HN 49643556, Sep 2026).",
        "evidence": "https://news.ycombinator.com/item?id=50352757",
    },
    "claude": {
        "product": "Claude / Claude Code (claude.ai login)",
        "setting": "Settings > Privacy > \"Help improve Claude\" (also /privacy-settings inside Claude Code)",
        "off_means": "Off",
        "url": "https://claude.ai/settings/data-privacy-controls",
        "applies": "Free, Pro, Max and Ultra. Team/Enterprise/API run under commercial terms.",
        "why": "On: chats and coding sessions may be trained on and kept 5 years. Off: 30 days (code.claude.com/docs/en/data-usage).",
        "evidence": "https://code.claude.com/docs/en/data-usage",
    },
    "gemini": {
        "product": "Gemini apps (gemini.google.com)",
        "setting": "Gemini Apps Activity / \"Keep Activity\"",
        "off_means": "Off (turning off history is the only training opt-out for personal accounts)",
        "url": "https://myactivity.google.com/product/gemini",
        "applies": "Personal Google accounts, including paid subscribers.",
        "why": "Trains on saved chat history, human reviewers may read chats (HN 50363461, Nov 4 2026).",
        "evidence": "https://news.ycombinator.com/item?id=50363461",
    },
    "copilot": {
        "product": "GitHub Copilot (individual plans)",
        "setting": "Settings > Copilot > Features > Privacy > \"Allow GitHub to use my data for AI model training\"",
        "off_means": "Disabled",
        "url": "https://github.com/settings/copilot/features",
        "applies": "Copilot Free, Pro, Pro+ and Max. Business/Enterprise seats are excluded.",
        "why": "On by default since Apr 24 2026 unless you had opted out of product-improvement collection before.",
        "evidence": "https://github.blog/changelog/2026-03-25-updates-to-our-privacy-statement-and-terms-of-service-how-we-use-your-data/",
    },
    "mistral": {
        "product": "Mistral Le Chat",
        "setting": "Le Chat settings > Privacy (training on your inputs/outputs)",
        "off_means": "Off",
        "url": "https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training",
        "applies": "Free and Pro. Team/Enterprise have an admin control.",
        "why": "Pro is opted in to training by default (HN 49535284, Sep 2026).",
        "evidence": "https://news.ycombinator.com/item?id=49535284",
    },
    "cursor": {
        "product": "Cursor",
        "setting": "Cursor Settings > General > Privacy Mode (or the dashboard)",
        "off_means": "Privacy Mode on (no training)",
        "url": "https://cursor.com/dashboard?tab=settings",
        "applies": "All plans; on by default for Enterprise teams.",
        "why": "optout also reads Cursor's locally cached privacy mode (see `optout scan`). Installing the iOS app reportedly moved users off legacy no-storage mode (HN 48737226).",
        "evidence": "https://news.ycombinator.com/item?id=48737226",
    },
}


def _path(home=None):
    return os.path.join(state_dir(home), "attestations.json")


def load(home=None):
    try:
        with open(_path(home), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return {}


def record(vendor, state, note="", home=None, when=None):
    if vendor not in ACCOUNTS:
        raise KeyError(vendor)
    data = load(home)
    when = when or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    data.setdefault(vendor, []).append({"at": when.isoformat(), "state": state, "note": note})
    p = _path(home)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, p)
    return data[vendor][-1]


def latest(vendor, home=None, data=None):
    data = load(home) if data is None else data
    items = data.get(vendor) or []
    return items[-1] if items else None


def age_days(entry, now=None):
    now = now or _dt.datetime.now(_dt.timezone.utc)
    at = _dt.datetime.fromisoformat(entry["at"])
    if at.tzinfo is None:
        at = at.replace(tzinfo=_dt.timezone.utc)
    return (now - at).total_seconds() / 86400.0


def status(vendor, max_age=14, home=None, data=None, now=None):
    """Return (status, detail) for one account: ok / bad / stale / unverified."""
    e = latest(vendor, home, data)
    if not e:
        return "unverified", "never checked"
    days = age_days(e, now)
    when = e["at"][:10]
    if e["state"] != "off":
        return "bad", f"you recorded it ON on {when}"
    if days > max_age:
        return "stale", f"last seen off {when} ({int(days)}d ago, max {max_age}d)"
    return "ok", f"seen off {when} ({int(days)}d ago)"
