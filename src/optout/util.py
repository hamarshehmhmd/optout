"""Small helpers: tolerant JSON(C) and TOML readers, platform paths."""
import json
import os
import re
import sys

try:  # Python 3.11+
    import tomllib  # type: ignore
except ImportError:  # pragma: no cover - exercised on 3.9/3.10
    tomllib = None


def strip_jsonc(text):
    """Remove // and /* */ comments and trailing commas, keeping strings intact."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_jsonc(path):
    """Return (data, error). data is None when the file is missing."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return None, None
    except OSError as e:
        return None, str(e)
    if not text.strip():
        return {}, None
    try:
        return json.loads(text), None
    except ValueError:
        pass
    try:
        return json.loads(strip_jsonc(text)), None
    except ValueError as e:
        return None, f"cannot parse {path}: {e}"


def _toml_value(raw):
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true"
    if raw[:1] in ('"', "'"):
        q = raw[0]
        end = raw.find(q, 1)
        return raw[1:end] if end > 0 else raw[1:]
    m = re.match(r"^-?\d+", raw)
    if m:
        return int(m.group(0))
    return raw


def mini_toml(text):
    """Very small TOML subset reader: [tables], dotted keys, scalar values.
    Used only when tomllib is unavailable; enough for the keys optout reads."""
    data, table = {}, []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\[\s*([^\[\]]+?)\s*\]$", s)
        if m:
            table = [p.strip().strip('"') for p in m.group(1).split(".")]
            continue
        if s.startswith("[["):
            table = ["__array__"]
            continue
        m = re.match(r'^([A-Za-z0-9_\-\."]+)\s*=\s*(.+)$', s)
        if not m:
            continue
        val = m.group(2).split(" #")[0]
        keys = table + [p.strip('"') for p in m.group(1).split(".")]
        cur = data
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
            if not isinstance(cur, dict):
                break
        else:
            cur[keys[-1]] = _toml_value(val)
    return data


def load_toml(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return None, None
    except OSError as e:
        return None, str(e)
    if tomllib is not None:
        try:
            return tomllib.loads(raw.decode("utf-8")), None
        except Exception as e:  # noqa: BLE001 - report and fall back
            try:
                return mini_toml(raw.decode("utf-8", "replace")), f"partial parse of {path}: {e}"
            except Exception:  # pragma: no cover
                return None, str(e)
    return mini_toml(raw.decode("utf-8", "replace")), None


def dig(d, dotted, default=None):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def truthy(v):
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in ("", "0", "false", "no", "off")


def platform_name():
    if sys.platform == "darwin":
        return "mac"
    if os.name == "nt":
        return "windows"
    return "linux"


def app_config_dir(home, app, plat=None):
    """VS Code-family user data dir (contains User/settings.json)."""
    plat = plat or platform_name()
    if plat == "mac":
        return os.path.join(home, "Library", "Application Support", app)
    if plat == "windows":
        real = home == os.path.expanduser("~")
        appdata = (os.environ.get("APPDATA") if real else None) or os.path.join(home, "AppData", "Roaming")
        return os.path.join(appdata, app)
    xdg = os.environ.get("XDG_CONFIG_HOME") if home == os.path.expanduser("~") else None
    return os.path.join(xdg or os.path.join(home, ".config"), app)


def state_dir(home=None):
    env = os.environ.get("OPTOUT_STATE_DIR")
    if env:
        return env
    home = home or os.path.expanduser("~")
    plat = platform_name()
    if plat == "mac":
        return os.path.join(home, "Library", "Application Support", "optout")
    if plat == "windows":
        real = home == os.path.expanduser("~")
        return os.path.join((os.environ.get("LOCALAPPDATA") if real else None) or os.path.join(home, "AppData", "Local"), "optout")
    base = os.environ.get("XDG_STATE_HOME") if home == os.path.expanduser("~") else None
    return os.path.join(base or os.path.join(home, ".local", "state"), "optout")
