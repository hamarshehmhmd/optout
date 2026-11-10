"""Render the optout narrated demo: real command output + edge-tts narration.

Usage: python demo/render.py   (needs ffmpeg, edge-tts, Pillow, network)
"""
import asyncio
import os
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(ROOT, "demo.mp4")
SDKBIN = "/tmp/oovenv/bin"
SANDBOX = "/tmp/oodemo"
W, H, FPS = 1280, 720, 24
VOICE = "en-US-AndrewNeural"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BG, FG = (24, 26, 33), (220, 223, 228)
ANSI = {"31": (255, 95, 95), "32": (95, 215, 120), "33": (240, 200, 80),
        "2": (130, 135, 145), "36": (90, 200, 230), "35": (200, 140, 230), "1": FG}
PROMPT = "dev@laptop ~ $ "

SCENES = [
    {
        "kind": "title",
        "title": "optout",
        "sub": "you turned off \"train on my data\".\nis it still off?",
        "say": "This is opt out, a small open source command line tool that checks whether your A I training, "
               "telemetry and data sharing opt outs are actually still off, across all the A I tools on your machine.",
    },
    {
        "kind": "bullets",
        "title": "The problem",
        "bullets": [
            "Codex: \"Improve the model\" found back on (HN, Nov 3 2026)",
            "Copilot Free/Pro: trained on by default since Apr 24 2026",
            "Mistral Pro opted in by default; Cursor iOS app changed privacy mode",
            "Each CLI and editor adds its own telemetry and upload settings",
            "Nobody knows which of them are still off today",
        ],
        "say": "A company whose developers had all turned off data sharing found it switched back on in Codex. "
               "GitHub began training on Copilot Free and Pro data by default in April. Mistral Pro is opted in by default, "
               "and installing Cursor's phone app changed people's privacy mode. On top of the account toggles, every C L I "
               "and editor has its own telemetry, feedback upload and transcript settings. So on any given day, nobody can say "
               "which of them are still off.",
    },
    {
        "kind": "term",
        "cmds": ["optout --color always scan --only claude"],
        "say": "Here is a demo home folder with typical configs. opt out scan reads every setting locally, and nothing is sent "
               "anywhere. For Claude Code it finds usage metrics, feedback uploads and the transcript sharing survey still on, "
               "and ninety days of local transcripts. It's signed in to a claude dot A I account, where training is an account "
               "toggle no local file can show, so it's marked to do.",
    },
    {
        "kind": "term",
        "cmds": ["optout --color always scan --only codex,gemini"],
        "say": "Codex has analytics and feedback uploads on, and it's signed in with Chat G P T, so the Chat G P T data control "
               "decides training. Gemini C L I has usage statistics on, telemetry that includes prompt text, and a Gemini A P I "
               "key, which on the unpaid tier lets Google use your prompts.",
    },
    {
        "kind": "term",
        "cmds": ["optout --color always scan --only editors,aider"],
        "say": "V S code telemetry is at the default, all. Copilot is installed, so its account training toggle applies. "
               "And for Cursor, opt out reads the privacy mode that Cursor caches from your account. Here it's the strongest one, "
               "legacy no storage.",
    },
    {
        "kind": "term",
        "cmds": ["optout --color always fix --write", "optout scan --only claude,codex,aider | tail -1"],
        "say": "opt out fix writes the opt outs each vendor documents into your user config files. It's a dry run by default, "
               "it keeps a backup of every file, and it keeps the comments in your toml and json files. Every local warning is now "
               "gone. What's left are the account toggles.",
    },
    {
        "kind": "term",
        "cmds": ["optout --color always accounts | head -9", "optout attest claude off --note 'checked in browser'",
                 "optout --color always scan --only claude | tail -4"],
        "say": "Those live on vendor servers, behind your login, so opt out can't read them, and it doesn't pretend to. "
               "opt out accounts lists the exact setting and link for each one. After you check, you record it, and the record "
               "goes stale after fourteen days, so you're reminded to look again.",
    },
    {
        "kind": "term",
        "cmds": ["optout baseline", "python3 simulate_cursor_ios_install.py",
                 "optout --color always drift"],
        "say": "Now drift. Save a baseline. Here I simulate what users reported after installing Cursor on i O S: the privacy mode "
               "moves from no storage to the looser no training mode. Both still count as privacy mode, but opt out drift "
               "flags it as weaker and exits with code three, so a daily cron job can alert you.",
    },
    {
        "kind": "term",
        "cmds": ["optout --color always terms --only anthropic,github,cursor",
                 "optout terms --pages acme.json >/dev/null; sed -i 's/do not use/may use/' acme-privacy.html",
                 "optout --color always terms --pages acme.json --diff"],
        "say": "Vendors also change the rules themselves. opt out terms takes a snapshot of each vendor's privacy and terms "
               "pages, live here, and on the next run it shows exactly what changed. This example vendor quietly changed "
               "do not use to may use.",
    },
    {
        "kind": "bullets",
        "title": "Limits",
        "bullets": [
            "Can't read server-side toggles: it records your checks instead",
            "Cursor's cached mode is only as fresh as Cursor's last sync",
            "Vendors rename settings; each rule cites the doc it's based on",
            "Some sites block scripts (openai.com returns 403)",
        ],
        "say": "The limits. It can't read server side toggles, it only records your checks. Cursor's cached mode is only as "
               "fresh as Cursor's last sync. Vendors rename settings, so each rule cites its source. And some sites, like "
               "open A I dot com, block scripted fetches.",
    },
    {
        "kind": "bullets",
        "title": "Try it",
        "bullets": [
            "curl -fsSL https://raw.githubusercontent.com/",
            "   hamarshehmhmd/optout/main/install.sh | sh",
            "optout   ·   optout fix --write   ·   optout drift",
            "github.com/hamarshehmhmd/optout",
            "GNU AGPL-3.0-or-later (commercial licenses available)",
        ],
        "say": "Install it with the one line installer and run opt out. It has no dependencies, and it's licensed under the "
               "GNU Affero General Public License version 3 or later, with commercial licenses available from the author. "
               "It's on GitHub at hamarsheh m h m d slash opt out.",
    },
]


async def tts(text, path):
    import edge_tts
    for attempt in range(8):
        try:
            await edge_tts.Communicate(text, VOICE, rate="+4%").save(path)
            return
        except Exception:
            if os.path.exists(path):
                os.remove(path)
            if attempt == 7:
                raise
            await asyncio.sleep(5)


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        text=True,
    )
    return float(out.strip())


EXPORTS = {}


def run_cmd(cmd, cwd):
    if cmd.startswith("export ") and "=" in cmd:
        k, v = cmd[7:].split("=", 1)
        EXPORTS[k] = v
        return ""
    env = dict(os.environ, FORCE_COLOR="1", **EXPORTS)
    env.pop("NO_COLOR", None)
    env["PATH"] = SDKBIN + os.pathsep + env["PATH"]
    env["COLUMNS"] = "120"
    p = subprocess.run(
        ["bash", "-c", "shopt -s nullglob; " + cmd],
        cwd=cwd, capture_output=True, text=True, env=env,
    )
    return (p.stdout + p.stderr).rstrip("\n")


def parse_ansi(line):
    spans, color, bold = [], FG, False
    for part in re.split(r"(\x1b\[[0-9;]*m)", line):
        m = re.match(r"\x1b\[([0-9;]*)m", part)
        if m:
            for code in (m.group(1) or "0").split(";"):
                if code == "0":
                    color, bold = FG, False
                elif code == "1":
                    bold = True
                elif code in ANSI:
                    color = ANSI[code]
        elif part:
            spans.append((part, color, bold))
    return spans


class Term:
    def __init__(self):
        self.font = ImageFont.truetype(MONO, 14)
        self.bold = ImageFont.truetype(MONO_B, 14)
        self.cw = self.font.getlength("M")
        self.lh = 20
        self.cols = int((W - 80) / self.cw)

    def wrap(self, spans):
        lines, cur, n = [], [], 0
        for text, c, b in spans:
            while text:
                room = self.cols - n
                if len(text) <= room:
                    cur.append((text, c, b)); n += len(text); text = ""
                else:
                    cut = text.rfind(" ", 0, room + 1)
                    cut = cut if cut > 0 else room
                    cur.append((text[:cut], c, b)); lines.append(cur); cur, n = [], 0
                    text = "    " + text[cut:].lstrip(" ")
        lines.append(cur)
        return lines

    def frame(self, lines, cursor=False):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([20, 14, W - 20, H - 14], 12, fill=(30, 33, 41), outline=(60, 64, 76))
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([40 + i * 24, 30, 54 + i * 24, 44], fill=c)
        d.text((W // 2, 37), "~ — bash", font=ImageFont.truetype(SANS, 15), fill=(150, 155, 165), anchor="mm")
        visible = lines[-30:]
        y = 64
        for ln in visible:
            x = 40
            for text, c, b in ln:
                d.text((x, y), text, font=self.bold if b else self.font, fill=c)
                x += self.cw * len(text)
            y += self.lh
        if cursor:
            last = visible[-1] if visible else []
            x = 40 + self.cw * sum(len(t) for t, _, _ in last)
            d.rectangle([x, y - self.lh + 3, x + self.cw - 2, y - 4], fill=FG)
        return img


def card(scene):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if scene["kind"] == "title":
        d.text((W // 2, 280), scene["title"], font=ImageFont.truetype(MONO_B, 78), fill=(95, 215, 120), anchor="mm")
        d.multiline_text((W // 2, 420), scene["sub"], font=ImageFont.truetype(SANS, 32), fill=FG, anchor="mm",
                         align="center", spacing=12)
        d.text((W // 2, 620), "github.com/hamarshehmhmd/optout  ·  scan · fix · attest · drift · terms  ·  GNU AGPL-3.0",
               font=ImageFont.truetype(SANS, 20), fill=(150, 155, 165), anchor="mm")
    else:
        d.text((90, 90), scene["title"], font=ImageFont.truetype(SANS_B, 52), fill=(95, 215, 120))
        f = ImageFont.truetype(SANS, 29)
        y = 200
        for b in scene["bullets"]:
            if b and not b.startswith("   "):
                d.text((90, y), "•", font=f, fill=(240, 200, 80))
            d.text((130, y), b.strip(), font=f, fill=FG)
            y += 58 if b.startswith("   ") or not b else 62
    return img


class Writer:
    def __init__(self, path, audio):
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio,
             "-af", "apad", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
             "-shortest", path],
            stdin=subprocess.PIPE,
        )
        self.n = 0

    def put(self, img, count=1):
        data = img.tobytes()
        for _ in range(count):
            self.p.stdin.write(data)
        self.n += count

    def close(self):
        self.p.stdin.close()
        self.p.wait()
        if self.p.returncode:
            sys.exit("ffmpeg failed")


def _cap_output(out):
    lines = out.splitlines()
    if len(lines) > 26:
        lines = lines[:24] + ["…", lines[-1]]
    return "\n".join(lines)


def render_scene(i, scene, workdir):
    audio = os.path.join(BUILD, f"s{i}.mp3")
    if not os.path.exists(audio):
        asyncio.run(tts(scene["say"], audio))
    total = int((duration(audio) + 0.7) * FPS)
    path = os.path.join(BUILD, f"s{i}.mp4")
    w = Writer(path, audio)
    if scene["kind"] != "term":
        w.put(card(scene), total)
        w.close()
        return path
    t = Term()
    shown = scene.get("show", scene["cmds"])
    outputs = [_cap_output(run_cmd(c, workdir)) for c in scene["cmds"]]
    # If show has more lines than cmds (a command displayed as several visual lines
    # that map to one executed command), join show into one typed command per output.
    if len(shown) != len(outputs):
        if len(outputs) == 1:
            shown = [" ".join(s.rstrip("\\").strip() for s in shown)]
        elif len(shown) > len(outputs):
            # first N-1 outputs map 1:1; remaining show lines are the last command
            shown = list(shown[: len(outputs) - 1]) + [
                " ".join(s.rstrip("\\").strip() for s in shown[len(outputs) - 1 :])
            ]
    steps = list(zip(shown, outputs))
    typing = sum(len(s) for s, _ in steps) / 32 * FPS
    pause = max(6, int((total - typing) / max(1, len(steps))) - 4)
    lines = []
    for cmd, out in steps:
        prompt = [(PROMPT, (95, 215, 120), True)]
        for k in range(0, len(cmd) + 1, 2):
            frame = t.frame(lines + t.wrap(prompt + [(cmd[:k], FG, False)]), cursor=True)
            w.put(frame)
        lines += t.wrap(prompt + [(cmd, FG, False)])
        for ol in out.splitlines():
            lines += t.wrap(parse_ansi(ol))
        lines.append([])
        hold = min(pause, max(0, total - w.n))
        w.put(t.frame(lines), hold)
    final = t.frame(lines + t.wrap([(PROMPT, (95, 215, 120), True)]), cursor=True)
    if w.n < total:
        w.put(final, total - w.n)
    w.close()
    return path


def main():
    os.makedirs(BUILD, exist_ok=True)
    if os.path.exists(SANDBOX):
        shutil.rmtree(SANDBOX)
    os.makedirs(SANDBOX)
    home = os.path.join(SANDBOX, "demo-home")
    subprocess.run([sys.executable, os.path.join(ROOT, "examples", "make_demo_home.py"), home], check=True)
    shutil.copy(os.path.join(HERE, "simulate_cursor_ios_install.py"), SANDBOX)
    shutil.copy(os.path.join(HERE, "acme-privacy.html"), SANDBOX)
    with open(os.path.join(SANDBOX, "acme.json"), "w") as fh:
        fh.write('{"pages": [{"id": "acme-ai-privacy", "vendor": "Acme AI", "url": "file://%s/acme-privacy.html"}]}' % SANDBOX)
    EXPORTS["OPTOUT_HOME"] = home
    EXPORTS["OPTOUT_STATE_DIR"] = os.path.join(home, ".local", "state", "optout")
    parts = [render_scene(i, s, SANDBOX) for i, s in enumerate(SCENES)]
    with open(os.path.join(BUILD, "list.txt"), "w") as fh:
        fh.writelines(f"file '{p}'\n" for p in parts)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i",
         os.path.join(BUILD, "list.txt"), "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", OUT],
        check=True,
    )
    with open(os.path.join(BUILD, "narration.txt"), "w") as fh:
        fh.write("\n\n".join(s["say"] for s in SCENES) + "\n")
    print(OUT, round(duration(OUT), 1), "s")


if __name__ == "__main__":
    main()
