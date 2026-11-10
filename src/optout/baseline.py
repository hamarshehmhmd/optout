"""Remember today's state; flag anything that got weaker since."""
import datetime as _dt
import json
import os

from .checks import STATUS_RANK
from .util import state_dir


def _path(home=None):
    return os.path.join(state_dir(home), "baseline.json")


def save(findings, home=None):
    p = _path(home)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = {"saved": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
            "findings": {f["id"]: {"status": f["status"], "value": f["value"], "tool": f["tool"], "title": f["title"],
                                  "strength": f.get("strength", 0)}
                         for f in findings}}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    return p


def load(home=None):
    try:
        with open(_path(home), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return None


def compare(base, findings):
    """Return list of (kind, id, before, after, finding) where kind is weaker/better/changed/new/gone."""
    out = []
    old = base["findings"]
    now = {f["id"]: f for f in findings}
    for fid, f in now.items():
        b = old.get(fid)
        if b is None:
            if STATUS_RANK.get(f["status"], 0) >= 2:
                out.append(("new", fid, None, f, f))
            continue
        rb, ra = STATUS_RANK.get(b["status"], 0), STATUS_RANK.get(f["status"], 0)
        if ra > rb:
            out.append(("weaker", fid, b, f, f))
        elif ra < rb:
            out.append(("better", fid, b, f, f))
        elif f.get("strength", 0) < b.get("strength", 0):
            out.append(("weaker", fid, b, f, f))
        elif f.get("strength", 0) > b.get("strength", 0):
            out.append(("better", fid, b, f, f))
        elif b["value"] != f["value"]:
            out.append(("changed", fid, b, f, f))
    for fid, b in old.items():
        if fid not in now:
            out.append(("gone", fid, b, None, None))
    return out
