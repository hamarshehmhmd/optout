"""optout command line."""
import argparse
import json
import os
import sys
import webbrowser

from . import __version__, accounts, baseline, checks, fix, terms

C = {"ok": "32", "info": "2", "warn": "33", "bad": "31", "unknown": "35", "unverified": "35", "stale": "33",
     "same": "2", "new": "36", "changed": "31", "error": "35", "weaker": "31", "better": "32", "gone": "2"}
ICON = {"ok": "OK  ", "info": "info", "warn": "WARN", "bad": "BAD ", "unknown": "??  ", "unverified": "TODO",
        "stale": "OLD "}
USE_COLOR = False


def col(code, s):
    return f"\x1b[{code}m{s}\x1b[0m" if USE_COLOR else s


def bold(s):
    return col("1", s)


def _setup_color(mode):
    global USE_COLOR
    if mode == "always":
        USE_COLOR = True
    elif mode == "never":
        USE_COLOR = False
    else:
        USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _ctx(a):
    return checks.Ctx(home=a.home, max_age=a.max_age)


def _only(a):
    return set(x.strip() for x in a.only.split(",")) if getattr(a, "only", None) else None


def render_table(findings, out=None, verbose=False):
    out = out or sys.stdout
    if not findings:
        print("No supported AI tools found (Claude Code, Codex, Gemini CLI, Cursor, VS Code, Windsurf, Aider).", file=out)
        return
    tool = None
    for f in findings:
        if f["tool"] != tool:
            tool = f["tool"]
            print(bold(tool), file=out)
        st = f["status"]
        print(f"  {col(C.get(st, '0'), ICON.get(st, st))}  {f['title']:<36} {f['value']}", file=out)
        if st not in ("ok", "info") or verbose:
            if f.get("detail"):
                print(col("2", f"        {f['detail']}"), file=out)
            if f.get("fix") and st not in ("ok", "info"):
                print(f"        -> {f['fix']}", file=out)
            if verbose and f.get("source"):
                print(col("2", f"        source: {f['source']}"), file=out)


def summary_line(findings):
    counts = {}
    for f in findings:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    order = ["bad", "warn", "stale", "unverified", "unknown", "ok", "info"]
    parts = [col(C[k], f"{counts[k]} {k}") for k in order if counts.get(k)]
    return ", ".join(parts) if parts else "nothing found"


def render_md(findings):
    lines = ["| Tool | Setting | Status | Value | Source | Doc |", "|---|---|---|---|---|---|"]
    for f in findings:
        lines.append(f"| {f['tool']} | {f['title']} | {f['status']} | {f['value']} | `{f['source']}` | {f['doc']} |")
    return "\n".join(lines)


FAIL_RANK = {"bad": 3, "warn": 2, "todo": 1, "never": 99}


def cmd_scan(a):
    findings = checks.scan(_ctx(a), _only(a))
    if a.format == "json":
        print(json.dumps({"version": __version__, "findings": findings}, indent=2))
    elif a.format == "md":
        print(render_md(findings))
    else:
        render_table(findings, verbose=a.verbose)
        print("\n" + summary_line(findings))
    return 1 if checks.worst(findings) >= FAIL_RANK[a.fail_on] else 0


def cmd_fix(a):
    p = fix.plan(a.home or os.path.expanduser("~"), only=_only(a))
    for path, why in p.skipped:
        print(col("33", f"skip  {path}: {why}"))
    if not p.changes:
        print("Nothing to change: every local opt-out optout knows about is already set.")
        return 0
    for ch in p.changes:
        print(f"{'set ' if a.write else 'would set'}  {bold(ch['tool'])}: {ch['what']}")
        print(col("2", f"        {ch['path'].replace(a.home or os.path.expanduser('~'), '~')}"))
    if a.write:
        backups = fix.apply(p)
        print(f"\nWrote {len(p.changes)} file(s); {len(backups)} backup(s) saved as *.optout-bak-*.")
        if any(c["tool"] == "Claude Code" for c in p.changes):
            print(col("2", "Note: DISABLE_TELEMETRY also turns off Claude Code feature flags, which can make Remote Control unavailable."))
    else:
        print("\nDry run. Re-run with --write to apply (backups are kept).")
    return 0


def cmd_accounts(a):
    data = accounts.load(a.home)
    if a.format == "json":
        out = {}
        for v, info in accounts.ACCOUNTS.items():
            st, det = accounts.status(v, a.max_age, data=data)
            out[v] = dict(info, status=st, detail=det, history=data.get(v, []))
        print(json.dumps(out, indent=2))
        return 0
    worst = 0
    for v, info in accounts.ACCOUNTS.items():
        st, det = accounts.status(v, a.max_age, data=data)
        worst = max(worst, {"ok": 0, "unverified": 1, "stale": 1, "bad": 3}[st])
        label = {"ok": "OK  ", "unverified": "TODO", "stale": "OLD ", "bad": "BAD "}[st]
        print(f"{col(C[st], label)}  {bold(v.ljust(10))} {info['product']}")
        print(f"        {info['setting']} -> {info['off_means']}")
        print(col("2", f"        {det} | {info['url']}"))
    print(col("2", "\nThese live on vendor servers; optout can't read them. Check, then record: optout attest <vendor> off"))
    return 0


def cmd_attest(a):
    if a.vendor not in accounts.ACCOUNTS:
        print(f"unknown vendor {a.vendor!r}; choose from: {', '.join(accounts.ACCOUNTS)}", file=sys.stderr)
        return 2
    e = accounts.record(a.vendor, a.state, a.note or "", a.home)
    print(f"recorded {a.vendor}: {a.state} at {e['at']}")
    if a.state == "on":
        print(col("31", f"  turn it off: {accounts.ACCOUNTS[a.vendor]['url']}"))
    return 0


def cmd_open(a):
    if a.vendor not in accounts.ACCOUNTS:
        print(f"unknown vendor {a.vendor!r}; choose from: {', '.join(accounts.ACCOUNTS)}", file=sys.stderr)
        return 2
    info = accounts.ACCOUNTS[a.vendor]
    print(f"{info['setting']} -> {info['off_means']}\n{info['url']}")
    if not a.print_only:
        webbrowser.open(info["url"])
    print(f"Then record what you saw: optout attest {a.vendor} off   (or: on)")
    return 0


def cmd_baseline(a):
    findings = checks.scan(_ctx(a))
    p = baseline.save(findings, a.home)
    print(f"saved baseline of {len(findings)} settings to {p}")
    return 0


def cmd_drift(a):
    base = baseline.load(a.home)
    if not base:
        print("No baseline yet. Run: optout baseline", file=sys.stderr)
        return 2
    findings = checks.scan(_ctx(a))
    diffs = baseline.compare(base, findings)
    weaker = [d for d in diffs if d[0] in ("weaker", "new")]
    if a.format == "json":
        print(json.dumps({"baseline": base["saved"], "changes": [
            {"kind": k, "id": i, "before": b, "after": (f and {"status": f["status"], "value": f["value"]})}
            for k, i, b, f, _ in diffs]}, indent=2))
        return 3 if weaker else 0
    print(f"compared with baseline from {base['saved']}")
    if not diffs:
        print(col("32", "no drift: every setting is as it was"))
    for kind, fid, b, f, _ in diffs:
        name = (f or b)["tool"] + ": " + (f or b)["title"]
        before = f"{b['status']} '{b['value']}'" if b else "(not present)"
        after = f"{f['status']} '{f['value']}'" if f else "(gone)"
        print(f"  {col(C[kind], kind.upper().ljust(7))} {name}\n        {before}  ->  {after}")
    if weaker:
        print(col("31", f"\n{len(weaker)} setting(s) got weaker since the baseline."))
    return 3 if weaker else 0


def cmd_terms(a):
    pages = terms.load_pages(a.pages)
    if a.only:
        ids = _only(a)
        pages = [p for p in pages if p["id"] in ids or p.get("vendor", "").lower() in ids]
    res = terms.check(pages, a.home)
    if a.format == "json":
        print(json.dumps([{k: v for k, v in r.items() if k != "diff"} for r in res], indent=2))
    else:
        for r in res:
            label = r["status"].upper().ljust(7)
            print(f"  {col(C[r['status']], label)} {r['id']:<28} {r['detail']}")
            if r["status"] == "changed" and a.diff:
                for ln in r["diff"][2:40]:
                    c = "32" if ln.startswith("+") else "31" if ln.startswith("-") else "2"
                    print("        " + col(c, ln[:150]))
                if len(r["diff"]) > 40:
                    print(col("2", f"        ... full diff: {r['diff_path']}"))
    return 3 if any(r["status"] == "changed" for r in res) else 0


def build_parser():
    ap = argparse.ArgumentParser(prog="optout", description="Keep AI training, telemetry and retention opt-outs actually off.")
    ap.add_argument("--version", action="version", version=f"optout {__version__}")
    ap.add_argument("--home", default=os.environ.get("OPTOUT_HOME"), help="home directory to inspect (default: $OPTOUT_HOME or yours)")
    ap.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    ap.add_argument("--max-age", type=int, default=14, help="days before an account check counts as stale (default 14)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="check local AI tool settings and account checks (default)")
    s.add_argument("--format", choices=["table", "json", "md"], default="table")
    s.add_argument("--only", help="comma list: claude,codex,gemini,editors,aider,accounts")
    s.add_argument("--fail-on", choices=["bad", "warn", "todo", "never"], default="bad",
                   help="exit 1 at this level or worse (default bad)")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_scan)
    f = sub.add_parser("fix", help="write the documented local opt-outs (dry run by default)")
    f.add_argument("--write", action="store_true")
    f.add_argument("--only", help="comma list: claude,codex,gemini,editors,aider")
    f.set_defaults(fn=cmd_fix)
    s = sub.add_parser("accounts", help="list server-side training toggles and when you last checked each")
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(fn=cmd_accounts)
    s = sub.add_parser("attest", help="record what you saw on a vendor settings page")
    s.add_argument("vendor")
    s.add_argument("state", choices=["off", "on"])
    s.add_argument("--note")
    s.set_defaults(fn=cmd_attest)
    s = sub.add_parser("open", help="open a vendor's data-control page")
    s.add_argument("vendor")
    s.add_argument("--print-only", action="store_true")
    s.set_defaults(fn=cmd_open)
    s = sub.add_parser("baseline", help="save the current state to detect drift later")
    s.set_defaults(fn=cmd_baseline)
    s = sub.add_parser("drift", help="what got weaker since the baseline? (exit 3 if anything did)")
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(fn=cmd_drift)
    s = sub.add_parser("terms", help="snapshot vendor privacy/terms pages; exit 3 when one changed")
    s.add_argument("--diff", action="store_true", help="show what changed")
    s.add_argument("--pages", help="JSON file with your own list of pages")
    s.add_argument("--only", help="comma list of page ids or vendors")
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(fn=cmd_terms)
    return ap


def main(argv=None):
    ap = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    a = ap.parse_args(argv)
    if not a.cmd:
        a = ap.parse_args(argv + ["scan"])
    if a.home:
        a.home = os.path.abspath(os.path.expanduser(a.home))
    _setup_color(a.color)
    try:
        return a.fn(a)
    except BrokenPipeError:  # pragma: no cover
        return 0


if __name__ == "__main__":
    sys.exit(main())
