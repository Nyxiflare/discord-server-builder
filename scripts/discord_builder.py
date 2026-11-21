#!/usr/bin/env python3
"""
discord_builder.py - build and maintain a Discord server from a JSON blueprint.

Commands
  validate BLUEPRINT                  offline check; prints the planned layout and image checks
  check                               test the bot token; list the bot's servers; invite link
  inspect --guild ID                  show roles, channels, emojis, stickers and free slots
  apply BLUEPRINT --guild ID          create whatever is missing (run with --dry-run first)
        --update                      also change existing items to match the blueprint:
                                      renames ("was"), topics, slowmode, access, category,
                                      role colour/permissions, order, and the bot's starter posts
        --confirm-delete              with --update: also delete what the blueprint's "remove" lists
  delete --guild ID [--channel N] [--role N] [--emoji N] [--sticker N] [--confirm-delete]
                                      delete named items; without --confirm-delete it only lists them
  undo RESULT.json [--dry-run]        delete exactly what earlier applies created

The bot token is read from the DISCORD_BOT_TOKEN environment variable, or from a .env file
(the current folder, or --env-file PATH). It is never printed.
Standard library only; Pillow is used for automatic image resizing if it is installed.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    from PIL import Image  # optional: only used to resize emoji/sticker images
    HAVE_PIL = True
except Exception:  # pragma: no cover
    HAVE_PIL = False

API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://skills.sh, 1.1) discord-server-builder"

# Permission name -> bit number (Discord API v10).
BITS = {
    "CREATE_INSTANT_INVITE": 0, "KICK_MEMBERS": 1, "BAN_MEMBERS": 2, "ADMINISTRATOR": 3,
    "MANAGE_CHANNELS": 4, "MANAGE_GUILD": 5, "ADD_REACTIONS": 6, "VIEW_AUDIT_LOG": 7,
    "PRIORITY_SPEAKER": 8, "STREAM": 9, "VIEW_CHANNEL": 10, "SEND_MESSAGES": 11,
    "SEND_TTS_MESSAGES": 12, "MANAGE_MESSAGES": 13, "EMBED_LINKS": 14, "ATTACH_FILES": 15,
    "READ_MESSAGE_HISTORY": 16, "MENTION_EVERYONE": 17, "USE_EXTERNAL_EMOJIS": 18,
    "VIEW_GUILD_INSIGHTS": 19, "CONNECT": 20, "SPEAK": 21, "MUTE_MEMBERS": 22,
    "DEAFEN_MEMBERS": 23, "MOVE_MEMBERS": 24, "USE_VAD": 25, "CHANGE_NICKNAME": 26,
    "MANAGE_NICKNAMES": 27, "MANAGE_ROLES": 28, "MANAGE_WEBHOOKS": 29,
    "MANAGE_GUILD_EXPRESSIONS": 30, "USE_APPLICATION_COMMANDS": 31, "REQUEST_TO_SPEAK": 32,
    "MANAGE_EVENTS": 33, "MANAGE_THREADS": 34, "CREATE_PUBLIC_THREADS": 35,
    "CREATE_PRIVATE_THREADS": 36, "USE_EXTERNAL_STICKERS": 37, "SEND_MESSAGES_IN_THREADS": 38,
    "MODERATE_MEMBERS": 40, "CREATE_GUILD_EXPRESSIONS": 43, "SEND_VOICE_MESSAGES": 46,
    "SEND_POLLS": 49,
}


def perm(*names: str) -> int:
    value = 0
    for n in names:
        value |= 1 << BITS[n.upper()]
    return value


ADMIN_BIT = perm("ADMINISTRATOR")

_MEMBER = [
    "VIEW_CHANNEL", "SEND_MESSAGES", "READ_MESSAGE_HISTORY", "ADD_REACTIONS", "EMBED_LINKS",
    "ATTACH_FILES", "USE_EXTERNAL_EMOJIS", "CONNECT", "SPEAK", "USE_VAD", "STREAM",
    "CHANGE_NICKNAME", "CREATE_PUBLIC_THREADS", "SEND_MESSAGES_IN_THREADS",
    "USE_APPLICATION_COMMANDS", "SEND_VOICE_MESSAGES", "SEND_POLLS",
]
_MOD = _MEMBER + [
    "MANAGE_MESSAGES", "KICK_MEMBERS", "MODERATE_MEMBERS", "MANAGE_THREADS", "MUTE_MEMBERS",
    "DEAFEN_MEMBERS", "MOVE_MEMBERS", "MANAGE_NICKNAMES", "VIEW_AUDIT_LOG",
]
_ADMIN = _MOD + [
    "BAN_MEMBERS", "MANAGE_CHANNELS", "MANAGE_ROLES", "MANAGE_GUILD", "MANAGE_EVENTS",
    "MANAGE_WEBHOOKS", "MANAGE_GUILD_EXPRESSIONS", "MENTION_EVERYONE", "CREATE_INSTANT_INVITE",
]
# Presets deliberately never grant ADMINISTRATOR; list it explicitly if truly wanted.
PRESETS = {"none": [], "member": _MEMBER, "moderator": _MOD, "admin": _ADMIN}

TYPES = {"text": 0, "voice": 2, "category": 4, "announcement": 5, "stage": 13, "forum": 15}
TYPE_NAMES = {v: k for k, v in TYPES.items()}
FALLBACK = {"announcement": "text", "forum": "text", "stage": "voice"}  # when Community is off
ACCESS_KEYS = ("private_to", "read_only", "writers")

# Expression slots by server boost level (premium_tier).
EMOJI_SLOTS = {0: 50, 1: 100, 2: 150, 3: 250}   # each for static and for animated
STICKER_SLOTS = {0: 5, 1: 15, 2: 30, 3: 60}
EMOJI_MAX_BYTES = 256 * 1024
STICKER_MAX_BYTES = 512 * 1024
MIME = {"png": "image/png", "gif": "image/gif", "jpeg": "image/jpeg", "webp": "image/webp",
        "lottie": "application/json"}
EMOJI_NAME = re.compile(r"^[A-Za-z0-9_]{2,32}$")


def family(type_name: str) -> str:
    if type_name == "category":
        return "category"
    return "voice" if type_name in ("voice", "stage") else "text"


def norm(name: str, type_name: str) -> str:
    n = name.strip().lower()
    if family(type_name) == "text":
        n = "-".join(n.split())  # Discord turns spaces in text channel names into hyphens
    return n


def parse_color(c) -> int:
    if isinstance(c, int):
        return c
    s = str(c).strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"color '{c}' should look like #5865F2")
    return int(s, 16)


def role_permissions(r: dict) -> int:
    p = r.get("permissions", "none")
    names = PRESETS[p] if isinstance(p, str) else p
    return perm(*names) if names else 0


def out(s: str = "") -> None:
    print(s, flush=True)


# --------------------------------------------------------------------------- images

def sniff(data: bytes) -> str | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.lstrip()[:1] == b"{":
        return "lottie"
    return None


def is_animated(data: bytes, fmt: str) -> bool:
    if fmt == "gif":
        if HAVE_PIL:
            try:
                return getattr(Image.open(io.BytesIO(data)), "n_frames", 1) > 1
            except Exception:
                pass
        return data.count(b"\x21\xf9\x04") > 1  # more than one graphic-control block
    if fmt == "png":
        idat = data.find(b"IDAT")
        return b"acTL" in data[: idat if idat > 0 else len(data)]  # APNG
    if fmt == "webp":
        return b"ANMF" in data
    return False


def image_size(data: bytes, fmt: str):
    if HAVE_PIL and fmt != "lottie":
        try:
            return Image.open(io.BytesIO(data)).size
        except Exception:
            return None
    if fmt == "png" and len(data) > 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if fmt == "gif" and len(data) > 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    return None


def prepare_image(path: Path, kind: str):
    """Return (bytes, fmt, animated, note). Raises ValueError with a plain fix-it message."""
    if not path.is_file():
        raise ValueError(f"{path.name}: file not found ({path})")
    data = path.read_bytes()
    fmt = sniff(data)
    allowed = {"emoji": ("png", "jpeg", "gif", "webp"), "sticker": ("png", "gif", "lottie")}[kind]
    if fmt not in allowed:
        raise ValueError(f"{path.name}: {fmt or 'unknown'} files can't be used as {kind}s "
                         f"(use {', '.join(allowed)}).")
    limit = EMOJI_MAX_BYTES if kind == "emoji" else STICKER_MAX_BYTES
    if fmt == "lottie":
        if len(data) > limit:
            raise ValueError(f"{path.name}: Lottie file is {len(data)//1024} KB; the limit is 512 KB.")
        return data, fmt, True, "Lottie stickers only work on verified/partnered servers"
    animated = is_animated(data, fmt)
    size = image_size(data, fmt)
    problems = []
    if len(data) > limit:
        problems.append(f"{len(data)//1024} KB (limit {limit//1024} KB)")
    if kind == "sticker" and size and tuple(size) != (320, 320):
        problems.append(f"{size[0]}x{size[1]} px (stickers must be 320x320)")
    if not problems:
        return data, fmt, animated, ""
    what = " and ".join(problems)
    if animated:
        raise ValueError(f"{path.name}: animated {kind} is {what}. Resize/compress it "
                         f"(for example with ezgif.com) and try again.")
    if not HAVE_PIL:
        raise ValueError(f"{path.name}: {what}. Install Pillow (pip install pillow) to fix "
                         f"this automatically, or resize the image yourself.")
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    box = 128 if kind == "emoji" else 320
    img.thumbnail((box, box), Image.LANCZOS)
    if kind == "sticker":
        canvas = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        canvas.paste(img, ((320 - img.width) // 2, (320 - img.height) // 2), img)
        img = canvas
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    new = buf.getvalue()
    if len(new) > limit:
        raise ValueError(f"{path.name}: still {len(new)//1024} KB after resizing - use a simpler image.")
    return new, "png", False, f"auto-resized to {img.width}x{img.height} PNG ({len(new)//1024} KB)"


# --------------------------------------------------------------------------- blueprint

def load_blueprint(path: str):
    try:
        bp = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        sys.exit(f"Blueprint not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"Blueprint is not valid JSON ({path}, line {e.lineno}): {e.msg}")

    base = Path(path).resolve().parent
    errors: list[str] = []
    warnings: list[str] = []
    role_names: set[str] = set()

    def check_was(where: str, item: dict) -> None:
        if "was" in item and (not isinstance(item["was"], str) or not item["was"].strip()):
            errors.append(f"{where}: 'was' must be the item's current name.")

    for r in bp.get("roles", []):
        n = (r.get("name") or "").strip()
        if not n:
            errors.append("A role has no name.")
            continue
        check_was(f"Role '{n}'", r)
        if n.lower() in ("@everyone", "everyone"):
            errors.append("Don't define a role called @everyone - every server already has it.")
        if len(n) > 100:
            errors.append(f"Role '{n[:30]}...' name is longer than 100 characters.")
        if n.lower() in role_names:
            errors.append(f"Role '{n}' is defined twice.")
        role_names.add(n.lower())
        p = r.get("permissions", "none")
        if isinstance(p, str):
            if p not in PRESETS:
                errors.append(f"Role '{n}': unknown preset '{p}' (use {', '.join(PRESETS)} or a list).")
        elif isinstance(p, list):
            bad = [x for x in p if str(x).upper() not in BITS]
            if bad:
                errors.append(f"Role '{n}': unknown permissions {bad}.")
            if any(str(x).upper() == "ADMINISTRATOR" for x in p):
                warnings.append(f"Role '{n}' gets ADMINISTRATOR (full control). Only give it to people you fully trust.")
        else:
            errors.append(f"Role '{n}': permissions must be a preset name or a list.")
        if "color" in r:
            try:
                parse_color(r["color"])
            except ValueError as e:
                errors.append(f"Role '{n}': {e}")

    def check_access(where: str, a: dict) -> None:
        for key in ("private_to", "writers"):
            v = a.get(key)
            if v is None:
                continue
            if not isinstance(v, list):
                errors.append(f"{where}: '{key}' must be a list of role names.")
                continue
            for rn in v:
                if str(rn).lower() not in role_names and str(rn).lower() != "@everyone":
                    warnings.append(f"{where}: role '{rn}' is not in this blueprint (fine only if it already exists in the server).")
        if a.get("writers") and not a.get("read_only"):
            warnings.append(f"{where}: 'writers' has no effect unless read_only is true.")

    def check_channel(where: str, ch: dict) -> None:
        n = (ch.get("name") or "").strip()
        if not n:
            errors.append(f"{where}: a channel has no name.")
            return
        check_was(f"{where}/{n}", ch)
        if len(n) > 100:
            errors.append(f"{where}/{n[:30]}: name longer than 100 characters.")
        t = ch.get("type", "text")
        if t not in TYPES or t == "category":
            errors.append(f"{where}/{n}: unknown type '{t}' (text, voice, announcement, forum, stage).")
        if len(ch.get("topic", "") or "") > 1024:
            errors.append(f"{where}/{n}: topic longer than 1024 characters.")
        sm = ch.get("slowmode", 0)
        if not isinstance(sm, int) or not 0 <= sm <= 21600:
            errors.append(f"{where}/{n}: slowmode must be 0-21600 seconds.")
        if ch.get("message") and t in ("voice", "stage"):
            warnings.append(f"{where}/{n}: starter messages are skipped for voice/stage channels.")
        check_access(f"{where}/{n}", ch)

    total = 0
    for ch in bp.get("channels", []):
        check_channel("(no category)", ch)
        total += 1
    cat_names: set[str] = set()
    for c in bp.get("categories", []):
        cn = (c.get("name") or "").strip()
        if not cn:
            errors.append("A category has no name.")
            continue
        check_was(f"Category '{cn}'", c)
        if cn.lower() in cat_names:
            errors.append(f"Category '{cn}' is defined twice.")
        cat_names.add(cn.lower())
        check_access(cn, c)
        chans = c.get("channels", [])
        if len(chans) > 50:
            errors.append(f"Category '{cn}' has {len(chans)} channels; Discord allows 50.")
        seen: set[tuple] = set()
        for ch in chans:
            check_channel(cn, ch)
            k = (family(ch.get("type", "text")), norm(ch.get("name", ""), ch.get("type", "text")))
            if k in seen:
                errors.append(f"{cn}: channel '{ch.get('name')}' is listed twice.")
            seen.add(k)
        total += 1 + len(chans)
    if total > 500:
        errors.append(f"{total} channels; Discord allows 500.")
    elif total > 35:
        warnings.append(f"{total} channels+categories. New communities feel empty with this many - consider fewer.")

    names_seen: set[str] = set()
    for e in bp.get("emojis", []):
        n = str(e.get("name", ""))
        if not EMOJI_NAME.match(n):
            errors.append(f"Emoji '{n}': names are 2-32 characters, letters/numbers/underscores only.")
        if n.lower() in names_seen:
            errors.append(f"Emoji '{n}' is listed twice.")
        names_seen.add(n.lower())
        check_was(f"Emoji '{n}'", e)
        if not e.get("file"):
            errors.append(f"Emoji '{n}': needs a 'file'.")
        elif not (base / e["file"]).is_file():
            errors.append(f"Emoji '{n}': file not found: {e['file']}")
    names_seen = set()
    for s in bp.get("stickers", []):
        n = str(s.get("name", ""))
        if not 2 <= len(n) <= 30:
            errors.append(f"Sticker '{n}': name must be 2-30 characters.")
        if n.lower() in names_seen:
            errors.append(f"Sticker '{n}' is listed twice.")
        names_seen.add(n.lower())
        check_was(f"Sticker '{n}'", s)
        d = s.get("description", "")
        if d and not 2 <= len(d) <= 100:
            errors.append(f"Sticker '{n}': description must be 2-100 characters (or empty).")
        tags = str(s.get("tags", "")).strip()
        if not 1 <= len(tags) <= 200:
            errors.append(f"Sticker '{n}': 'tags' is required - the emoji name it suggests on, e.g. \"fire\".")
        if not s.get("file"):
            errors.append(f"Sticker '{n}': needs a 'file'.")
        elif not (base / s["file"]).is_file():
            errors.append(f"Sticker '{n}': file not found: {s['file']}")

    rm = bp.get("remove")
    if rm is not None:
        if not isinstance(rm, dict) or any(k not in ("channels", "roles", "emojis", "stickers") for k in rm):
            errors.append("'remove' must look like {\"channels\": [...], \"roles\": [...], \"emojis\": [...], \"stickers\": [...]}.")
        else:
            for k, v in rm.items():
                if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                    errors.append(f"remove.{k} must be a list of names.")
            for rn in rm.get("roles", []):
                if rn.lower() in role_names:
                    errors.append(f"Role '{rn}' is both defined and listed in remove.")
            if any(rm.values()):
                warnings.append("The 'remove' list only runs with apply --update --confirm-delete, after the user approves it.")
    return bp, errors, warnings


def merged_access(parent: dict | None, ch: dict) -> dict:
    a = {k: parent[k] for k in ACCESS_KEYS if parent and k in parent}
    a.update({k: ch[k] for k in ACCESS_KEYS if k in ch})
    return a


def describe(a: dict) -> str:
    parts = []
    if a.get("private_to"):
        parts.append("only " + ", ".join(a["private_to"]))
    if a.get("read_only"):
        w = a.get("writers") or []
        parts.append("read-only" + (f", posts by {', '.join(w)}" if w else ""))
    return f"  [{'; '.join(parts)}]" if parts else ""


ICON = {"text": "#", "announcement": "#(announce)", "forum": "#(forum)", "voice": "(voice)",
        "stage": "(stage)", "category": "[]"}


def print_plan(bp: dict) -> None:
    title = bp.get("server_name") or "server"
    out(f"Planned layout for: {title}")
    was = lambda x: f"  (renamed from '{x['was']}')" if x.get("was") else ""
    roles = bp.get("roles", [])
    if roles:
        out("\nRoles (highest first):")
        for r in roles:
            p = r.get("permissions", "none")
            label = p if isinstance(p, str) else f"{len(p)} custom permissions"
            out(f"  @{r['name']}  ({label}){was(r)}")
    out("\nChannels:")

    def line(ch, parent, indent):
        t = ch.get("type", "text")
        msg = "  +message" if ch.get("message") else ""
        if ch.get("pin") and ch.get("message"):
            msg += " (pinned)"
        out(f"{indent}{ICON[t]} {ch['name']}{describe(merged_access(parent, ch))}{msg}{was(ch)}")

    for ch in bp.get("channels", []):
        line(ch, None, "  ")
    for c in bp.get("categories", []):
        out(f"  [{c['name']}]{describe(merged_access(None, c))}{was(c)}")
        for ch in c.get("channels", []):
            line(ch, c, "      ")
    if bp.get("emojis"):
        out("\nEmojis:  " + "  ".join(f":{e['name']}:" for e in bp["emojis"]))
    if bp.get("stickers"):
        out("Stickers: " + ", ".join(s["name"] for s in bp["stickers"]))
    rm = bp.get("remove") or {}
    if any(rm.values()):
        out("\nTo delete (needs --update --confirm-delete):")
        for k, v in rm.items():
            for n in v:
                out(f"  - {k[:-1]}: {n}")


# --------------------------------------------------------------------------- HTTP

class DiscordError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        try:
            j = json.loads(body)
            self.code, self.msg = j.get("code"), j.get("message", body)
            if j.get("errors"):
                self.msg += " " + json.dumps(j["errors"])[:300]
        except Exception:
            self.code, self.msg = None, body[:300]
        super().__init__(f"HTTP {status}: {self.msg}")


class Client:
    def __init__(self, token: str):
        self._token = token

    def _send(self, method: str, path: str, data: bytes | None, content_type: str | None):
        for _ in range(6):
            headers = {"Authorization": f"Bot {self._token}", "User-Agent": USER_AGENT}
            if content_type:
                headers["Content-Type"] = content_type
            req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace")
                if e.code == 429:
                    try:
                        wait = float(json.loads(raw).get("retry_after", 1))
                    except Exception:
                        wait = 2.0
                    time.sleep(wait + 0.25)
                    continue
                raise DiscordError(e.code, raw) from None
            except urllib.error.URLError as e:
                sys.exit(f"Could not reach Discord: {e.reason}")
        raise DiscordError(429, '{"message": "rate limited repeatedly"}')

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        return self._send(method, path, data, "application/json" if data is not None else None)

    def call_multipart(self, method: str, path: str, fields: dict, file: tuple):
        boundary = "----dsb" + uuid.uuid4().hex
        parts = []
        for k, v in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        fname, blob, mime = file
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                     f"Content-Type: {mime}\r\n\r\n".encode() + blob + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self._send(method, path, b"".join(parts), f"multipart/form-data; boundary={boundary}")


def load_token(env_file: str | None) -> str:
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if tok:
        return tok
    path = Path(env_file) if env_file else Path.cwd() / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].strip()
            k, sep, v = line.partition("=")
            if sep and k.strip() == "DISCORD_BOT_TOKEN":
                v = v.strip().strip('"').strip("'")
                if v:
                    return v
    sys.exit(
        "No bot token found.\n"
        f"Create a file called .env in {path.parent} containing one line:\n"
        "  DISCORD_BOT_TOKEN=paste-your-bot-token-here\n"
        "(or set the DISCORD_BOT_TOKEN environment variable). Never paste the token into a chat."
    )


def explain(e: DiscordError) -> str:
    if e.status == 401:
        return "The bot token was rejected. Reset it in the Developer Portal (Bot tab) and update .env."
    if e.code == 30008:
        return "The server has no free emoji slots left (boost the server or delete some emojis)."
    if e.code == 30039:
        return "The server has no free sticker slots left (boost the server or delete some stickers)."
    if e.status == 403 or e.code == 50013:
        return ("Missing permissions. Make sure the bot was invited with Administrator (or Manage Roles, "
                "Manage Channels and Manage Expressions), and that its role is at the top of Server Settings > Roles.")
    if e.status == 404:
        return "Not found - is the bot actually in that server, and is the server ID right?"
    if e.code in (50045, 50138):
        return "That file is too big for Discord."
    return str(e)


def fetch_server(client: Client, gid: str, need_member: bool = True) -> dict:
    """Everything the commands need to know about a server, in one place."""
    me = client.call("GET", "/users/@me")
    guild = client.call("GET", f"/guilds/{gid}")
    s = {
        "me": me, "guild": guild,
        "roles": client.call("GET", f"/guilds/{gid}/roles"),
        "channels": client.call("GET", f"/guilds/{gid}/channels"),
        "emojis": client.call("GET", f"/guilds/{gid}/emojis") or [],
        "stickers": client.call("GET", f"/guilds/{gid}/stickers") or [],
        "bot_top": (0, 0),
    }
    if need_member:
        member = client.call("GET", f"/guilds/{gid}/members/{me['id']}")
        by_id = {r["id"]: r for r in s["roles"]}
        s["bot_top"] = max([rank(by_id[r]) for r in member.get("roles", []) if r in by_id] or [(0, 0)])
    return s


def rank(role: dict) -> tuple:
    """Discord's real role order: higher position wins; on equal positions the older role (lower id) wins."""
    return (role["position"], -int(role["id"]))


def role_protection(role: dict, gid: str, bot_top) -> str | None:
    if role["id"] == gid:
        return "@everyone can't be changed here"
    if role.get("managed"):
        return "managed by a bot or integration"
    if rank(role) >= bot_top:
        return "at or above the bot's own role"
    return None


# --------------------------------------------------------------------------- commands

def cmd_validate(args) -> int:
    bp, errors, warnings = load_blueprint(args.blueprint)
    print_plan(bp)
    base = Path(args.blueprint).resolve().parent
    for kind, items in (("emoji", bp.get("emojis", [])), ("sticker", bp.get("stickers", []))):
        for it in items:
            if not it.get("file") or not (base / it["file"]).is_file():
                continue
            try:
                _, fmt, animated, note = prepare_image(base / it["file"], kind)
                out(f"  {kind} {it['name']}: {fmt}{' (animated)' if animated else ''} OK" + (f" - {note}" if note else ""))
            except ValueError as e:
                errors.append(str(e))
    for w in warnings:
        out(f"\nWARNING: {w}")
    for e in errors:
        out(f"\nERROR: {e}")
    out("\nBlueprint OK." if not errors else f"\n{len(errors)} error(s) - fix them before applying.")
    return 1 if errors else 0


def cmd_check(args, client: Client | None = None) -> int:
    client = client or Client(load_token(args.env_file))
    try:
        me = client.call("GET", "/users/@me")
        guilds = client.call("GET", "/users/@me/guilds") or []
    except DiscordError as e:
        out(explain(e))
        return 1
    out(f"Token works. Bot: {me.get('username')} (id {me['id']})")
    invite = f"https://discord.com/oauth2/authorize?client_id={me['id']}&scope=bot&permissions=8"
    if guilds:
        out("\nServers the bot is in:")
        for g in guilds:
            out(f"  {g['name']}  -> --guild {g['id']}")
    else:
        out("\nThe bot is not in any server yet.")
    out(f"\nInvite link (Administrator, for setup):\n  {invite}")
    return 0


def cmd_inspect(args, client: Client | None = None) -> int:
    client = client or Client(load_token(args.env_file))
    gid = args.guild
    try:
        s = fetch_server(client, gid)
    except DiscordError as e:
        out(explain(e))
        return 1
    guild, roles, chans = s["guild"], s["roles"], s["channels"]
    tier = guild.get("premium_tier", 0)
    out(f"Server: {guild['name']}  (community features: {'on' if 'COMMUNITY' in guild.get('features', []) else 'off'}, boost level {tier})")
    out("\nRoles (highest first):")
    for r in sorted(roles, key=rank, reverse=True):
        lock = role_protection(r, gid, s["bot_top"])
        out(f"  @{r['name']}" + (f"  [locked: {lock}]" if lock and r["id"] != gid else ""))
    out("\nChannels:")
    cats = sorted([c for c in chans if c["type"] == 4], key=lambda c: c["position"])

    def kids(pid):
        return sorted([c for c in chans if c.get("parent_id") == pid and c["type"] != 4], key=lambda c: c["position"])
    for c in kids(None):
        out(f"  {ICON.get(TYPE_NAMES.get(c['type'], 'text'), '#')} {c['name']}")
    for cat in cats:
        out(f"  [{cat['name']}]")
        for c in kids(cat["id"]):
            out(f"      {ICON.get(TYPE_NAMES.get(c['type'], 'text'), '#')} {c['name']}")
    st = sum(1 for e in s["emojis"] if not e.get("animated"))
    an = len(s["emojis"]) - st
    out(f"\nEmojis: {st}/{EMOJI_SLOTS.get(tier, 50)} static, {an}/{EMOJI_SLOTS.get(tier, 50)} animated"
        + (":  " + " ".join(f":{e['name']}:" for e in s["emojis"]) if s["emojis"] else ""))
    out(f"Stickers: {len(s['stickers'])}/{STICKER_SLOTS.get(tier, 5)}"
        + (":  " + ", ".join(x["name"] for x in s["stickers"]) if s["stickers"] else ""))
    return 0


def build_overwrites(access: dict, guild_id: str, role_ids: dict, bot_id: str, fam: str, warn) -> list:
    view = perm("VIEW_CHANNEL")
    post = perm("CONNECT", "SPEAK") if fam == "voice" else perm(
        "SEND_MESSAGES", "SEND_MESSAGES_IN_THREADS", "CREATE_PUBLIC_THREADS")
    ow: dict[str, list] = {}

    def add(target: str, kind: int, allow: int = 0, deny: int = 0) -> None:
        cur = ow.setdefault(target, [0, 0, kind])
        cur[0] |= allow
        cur[1] |= deny

    def rid(name: str):
        r = role_ids.get(str(name).lower())
        if not r or str(r).startswith("new:"):
            if not r:
                warn(f"role '{name}' not found - skipped in permissions")
            return None
        return r

    if access.get("private_to"):
        add(guild_id, 0, deny=view)
        for rn in access["private_to"]:
            if (r := rid(rn)):
                add(r, 0, allow=view)
    if access.get("read_only"):
        add(guild_id, 0, deny=post)
        for rn in access.get("writers") or []:
            if (r := rid(rn)):
                add(r, 0, allow=post)
    if ow and bot_id:
        # Keep the bot able to see and post in locked channels (for starter messages).
        add(bot_id, 1, allow=perm("VIEW_CHANNEL", "SEND_MESSAGES", "READ_MESSAGE_HISTORY"))
    # A bit cannot be both allowed and denied on one target; allow wins.
    return [{"id": t, "type": k, "allow": str(a), "deny": str(d & ~a)} for t, (a, d, k) in ow.items()]


def ow_map(lst) -> dict:
    m = {}
    for o in lst or []:
        a, d = int(o.get("allow", 0)), int(o.get("deny", 0))
        if a or d:
            m[str(o["id"])] = (a, d)
    return m


def split_message(text: str, limit: int = 2000) -> list[str]:
    chunks, buf = [], ""
    for para in text.split("\n"):
        while len(para) > limit:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(para[:limit])
            para = para[limit:]
        candidate = f"{buf}\n{para}" if buf else para
        if len(candidate) > limit:
            chunks.append(buf)
            buf = para
        else:
            buf = candidate
    if buf.strip():
        chunks.append(buf)
    return chunks


def resolve_delete(names: dict, s: dict, gid: str):
    """Turn user-named items into delete targets. Refuses anything ambiguous or protected."""
    targets, refusals = [], []
    for n in names.get("channels", []):
        hits = [c for c in s["channels"]
                if c["name"].lower() == n.strip().lower()
                or norm(c["name"], TYPE_NAMES.get(c["type"], "text")) == norm(n, TYPE_NAMES.get(c["type"], "text"))]
        if not hits:
            refusals.append(f"channel '{n}': not found")
        elif len(hits) > 1:
            refusals.append(f"channel '{n}': {len(hits)} channels have this name - rename one or delete it in Discord")
        else:
            c = hits[0]
            kind = "category" if c["type"] == 4 else "channel"
            note = ""
            if kind == "category":
                inside = sum(1 for x in s["channels"] if x.get("parent_id") == c["id"])
                note = f" (its {inside} channel(s) are kept and move out of the category)" if inside else ""
            targets.append((kind, c["id"], f"{ICON.get(TYPE_NAMES.get(c['type'], 'text'), '#')} {c['name']}{note}"))
    for n in names.get("roles", []):
        hits = [r for r in s["roles"] if r["name"].lower() == n.strip().lower()]
        if not hits:
            refusals.append(f"role '{n}': not found")
        elif len(hits) > 1:
            refusals.append(f"role '{n}': {len(hits)} roles have this name - delete it in Discord")
        elif (why := role_protection(hits[0], gid, s["bot_top"])):
            refusals.append(f"role '{n}': not deleting - {why}")
        else:
            targets.append(("role", hits[0]["id"], f"@{hits[0]['name']}"))
    for kind, key in (("emoji", "emojis"), ("sticker", "stickers")):
        for n in names.get(key, []):
            hits = [x for x in s[key] if x["name"].lower() == n.strip().lower()]
            if not hits:
                refusals.append(f"{kind} '{n}': not found")
            else:
                targets.append((kind, hits[0]["id"], f"{kind} {hits[0]['name']}"))
    order = {"channel": 0, "category": 1, "role": 2, "emoji": 3, "sticker": 4}
    targets.sort(key=lambda t: order[t[0]])
    return targets, refusals


def do_delete(client: Client, gid: str, targets: list):
    done, problems = 0, []
    for kind, tid, label in targets:
        path = {"channel": f"/channels/{tid}", "category": f"/channels/{tid}",
                "role": f"/guilds/{gid}/roles/{tid}", "emoji": f"/guilds/{gid}/emojis/{tid}",
                "sticker": f"/guilds/{gid}/stickers/{tid}"}[kind]
        try:
            client.call("DELETE", path)
            done += 1
            time.sleep(0.3)
        except DiscordError as e:
            problems.append(f"{label}: {explain(e)}")
    return done, problems


def cmd_apply(args, client: Client | None = None) -> int:
    bp, errors, warnings = load_blueprint(args.blueprint)
    if errors:
        for e in errors:
            out(f"ERROR: {e}")
        out("Fix the blueprint first (run: validate).")
        return 1
    client = client or Client(load_token(args.env_file))
    dry = args.dry_run
    update = getattr(args, "update", False)
    confirm = getattr(args, "confirm_delete", False)
    base = Path(args.blueprint).resolve().parent
    gid = args.guild
    problems: list[str] = []
    notes: list[str] = []
    counts = {"created": 0, "changed": 0, "skipped": 0, "messages": 0, "deleted": 0}
    result = {"guild_id": gid, "roles": {}, "channels": {}, "emojis": {}, "stickers": {}, "messages": {}}
    would = " (would do)" if dry else ""

    def warn(msg: str) -> None:
        problems.append(msg)
        out(f"   ! {msg}")

    def note(msg: str) -> None:
        notes.append(msg)
        out(f"   i {msg}")

    try:
        s = fetch_server(client, gid, need_member=update)
    except DiscordError as e:
        out(explain(e))
        return 1
    me, guild = s["me"], s["guild"]
    existing_roles, existing_chans = s["roles"], s["channels"]
    community = "COMMUNITY" in guild.get("features", [])
    tier = guild.get("premium_tier", 0)
    mode = "UPDATE" if update else "CREATE"
    out(("DRY RUN - nothing will be changed. " if dry else "") + f"Mode: {mode}. Server: {guild['name']}")
    if not community:
        out("Community features are off: announcement/forum/stage channels will be created as text/voice.")
    bot_id = me["id"]
    role_by_name = {r["name"].lower(): r for r in existing_roles}
    role_ids = {k: r["id"] for k, r in role_by_name.items()}
    role_ids["@everyone"] = gid

    by_key, by_famname = {}, {}
    for c in existing_chans:
        tname = TYPE_NAMES.get(c["type"], "text")
        k = (family(tname), norm(c["name"], tname))
        by_key[(c.get("parent_id"),) + k] = c
        by_famname.setdefault(k, []).append(c)
    claimed: set[str] = set()

    chan_ids: dict[str, str] = {}
    for c in existing_chans:
        chan_ids.setdefault(norm(c["name"], TYPE_NAMES.get(c["type"], "text")), c["id"])
    emoji_by_name = {e["name"].lower(): e for e in s["emojis"]}

    def find_channel(token: str):
        t = norm(token, "text")
        if t in chan_ids:
            return chan_ids[t]
        # "rules" should also match decorated names like "📜┃rules" or "💬・rules"
        for name, cid in chan_ids.items():
            if name.endswith(t) and len(name) > len(t) and not name[-len(t) - 1].isalnum():
                return cid
        return None

    def fill(text: str) -> str:
        text = (text or "").replace("{server}", guild["name"])

        def chan(m):
            cid = find_channel(m.group(1))
            return f"<#{cid}>" if cid and not str(cid).startswith("new:") else f"#{m.group(1)}"

        def role(m):
            r = role_ids.get(m.group(1).strip().lower())
            return f"<@&{r}>" if r and not str(r).startswith("new:") and r != gid else f"@{m.group(1)}"

        def emo(m):
            e = emoji_by_name.get(m.group(1).lower())
            if e and not str(e.get("id", "")).startswith("new:"):
                return f"<{'a' if e.get('animated') else ''}:{e['name']}:{e['id']}>"
            return f":{m.group(1)}:"

        text = re.sub(r"\{#([^{}]+)\}", chan, text)
        text = re.sub(r"\{@([^{}]+)\}", role, text)
        return re.sub(r"\{:([A-Za-z0-9_]{2,32}):\}", emo, text)

    # ------------------------------------------------------------------ roles
    out("\nRoles:")
    role_order: list[str] = []
    for r in bp.get("roles", []):
        key = r["name"].lower()
        live = role_by_name.get(key)
        renamed_from = None
        if not live and update and r.get("was"):
            live = role_by_name.get(r["was"].lower())
            renamed_from = live["name"] if live else None
        if live:
            role_ids[key] = live["id"]
            role_order.append(live["id"])
            if not update:
                out(f"  = @{r['name']} (already exists)")
                counts["skipped"] += 1
                continue
            body, desc = {}, []
            if renamed_from:
                body["name"] = r["name"]
                desc.append(f"rename from @{renamed_from}")
            if "permissions" in r:
                want, have = role_permissions(r), int(live.get("permissions", 0))
                if have & ADMIN_BIT and not want & ADMIN_BIT:
                    want |= ADMIN_BIT  # never silently strip Administrator from an existing role
                if want != have:
                    body["permissions"] = str(want)
                    desc.append("permissions")
            if "color" in r and parse_color(r["color"]) != live.get("color", 0):
                body["color"] = parse_color(r["color"])
                desc.append("colour")
            for k in ("hoist", "mentionable"):
                if k in r and bool(r[k]) != bool(live.get(k)):
                    body[k] = bool(r[k])
                    desc.append(f"{k} {'on' if r[k] else 'off'}")
            if not body:
                out(f"  = @{r['name']} (no changes)")
                counts["skipped"] += 1
                continue
            lock = role_protection(live, gid, s["bot_top"])
            if lock:
                note(f"@{live['name']} not changed ({lock}): would have changed {', '.join(desc)}")
                continue
            out(f"  ~ @{r['name']}: {', '.join(desc)}{would}")
            counts["changed"] += 1
            if not dry:
                try:
                    client.call("PATCH", f"/guilds/{gid}/roles/{live['id']}", body)
                    time.sleep(0.3)
                except DiscordError as e:
                    warn(f"could not change @{live['name']}: {explain(e)}")
            continue
        body = {"name": r["name"], "permissions": str(role_permissions(r)),
                "hoist": bool(r.get("hoist", False)), "mentionable": bool(r.get("mentionable", False))}
        if "color" in r:
            body["color"] = parse_color(r["color"])
        if dry:
            role_ids[key] = f"new:{key}"
            out(f"  + @{r['name']} (would create)")
            counts["created"] += 1
            continue
        try:
            res = client.call("POST", f"/guilds/{gid}/roles", body)
            role_ids[key] = res["id"]
            role_order.append(res["id"])
            result["roles"][r["name"]] = res["id"]
            out(f"  + @{r['name']}")
            counts["created"] += 1
        except DiscordError as e:
            warn(f"could not create role {r['name']}: {explain(e)}")
        time.sleep(0.3)

    # ------------------------------------------------------------------ emojis & stickers
    if bp.get("emojis") or bp.get("stickers"):
        out(f"\nEmojis & stickers (boost level {tier}):")
    static_used = sum(1 for e in s["emojis"] if not e.get("animated"))
    anim_used = len(s["emojis"]) - static_used
    for e in bp.get("emojis", []):
        live = emoji_by_name.get(e["name"].lower())
        if not live and update and e.get("was"):
            old = emoji_by_name.get(e["was"].lower())
            if old:
                out(f"  ~ :{old['name']}: -> :{e['name']}:{would}")
                counts["changed"] += 1
                if not dry:
                    try:
                        client.call("PATCH", f"/guilds/{gid}/emojis/{old['id']}", {"name": e["name"]})
                    except DiscordError as ex:
                        warn(f"could not rename :{old['name']}: - {explain(ex)}")
                emoji_by_name[e["name"].lower()] = {**old, "name": e["name"]}
                continue
        if live:
            out(f"  = :{e['name']}: (already exists)")
            counts["skipped"] += 1
            continue
        try:
            blob, fmt, animated, inote = prepare_image(base / e["file"], "emoji")
        except ValueError as ex:
            warn(str(ex))
            continue
        cap = EMOJI_SLOTS.get(tier, 50)
        used = anim_used if animated else static_used
        if used >= cap:
            warn(f":{e['name']}: skipped - all {cap} {'animated' if animated else 'static'} emoji slots are used (boost level {tier})")
            continue
        out(f"  + :{e['name']}:{' (animated)' if animated else ''}" + (f" - {inote}" if inote else "") + (" (would upload)" if dry else ""))
        counts["created"] += 1
        if animated:
            anim_used += 1
        else:
            static_used += 1
        if dry:
            emoji_by_name[e["name"].lower()] = {"id": f"new:{e['name']}", "name": e["name"], "animated": animated}
            continue
        try:
            res = client.call("POST", f"/guilds/{gid}/emojis", {
                "name": e["name"], "image": f"data:{MIME[fmt]};base64,{base64.b64encode(blob).decode()}"})
            emoji_by_name[e["name"].lower()] = res
            result["emojis"][e["name"]] = res["id"]
        except DiscordError as ex:
            warn(f"could not upload :{e['name']}: - {explain(ex)}")
        time.sleep(0.3)

    sticker_by_name = {x["name"].lower(): x for x in s["stickers"]}
    sticker_used = len(s["stickers"])
    for st in bp.get("stickers", []):
        live = sticker_by_name.get(st["name"].lower())
        if not live and update and st.get("was"):
            live = sticker_by_name.get(st["was"].lower())
        if live:
            if not update:
                out(f"  = sticker {st['name']} (already exists)")
                counts["skipped"] += 1
                continue
            body = {}
            if live["name"] != st["name"]:
                body["name"] = st["name"]
            if "description" in st and (live.get("description") or "") != st["description"]:
                body["description"] = st["description"]
            if str(live.get("tags", "")) != str(st["tags"]):
                body["tags"] = str(st["tags"])
            if not body:
                out(f"  = sticker {st['name']} (no changes)")
                counts["skipped"] += 1
                continue
            out(f"  ~ sticker {live['name']}: {', '.join(body)}{would}")
            counts["changed"] += 1
            if not dry:
                try:
                    client.call("PATCH", f"/guilds/{gid}/stickers/{live['id']}", body)
                except DiscordError as ex:
                    warn(f"could not change sticker {live['name']}: {explain(ex)}")
            continue
        try:
            blob, fmt, animated, inote = prepare_image(base / st["file"], "sticker")
        except ValueError as ex:
            warn(str(ex))
            continue
        cap = STICKER_SLOTS.get(tier, 5)
        if sticker_used >= cap:
            warn(f"sticker {st['name']} skipped - all {cap} sticker slots are used (boost level {tier})")
            continue
        sticker_used += 1
        out(f"  + sticker {st['name']}" + (f" - {inote}" if inote else "") + (" (would upload)" if dry else ""))
        counts["created"] += 1
        if dry:
            continue
        try:
            res = client.call_multipart("POST", f"/guilds/{gid}/stickers", {
                "name": st["name"], "description": st.get("description", ""), "tags": str(st["tags"])},
                (Path(st["file"]).stem + (".json" if fmt == "lottie" else f".{fmt}"), blob, MIME[fmt]))
            result["stickers"][st["name"]] = res["id"]
        except DiscordError as ex:
            warn(f"could not upload sticker {st['name']}: {explain(ex)}")
        time.sleep(0.3)

    # ------------------------------------------------------------------ channels
    managed_targets = {gid, bot_id}
    blueprint_role_names = {r["name"].lower() for r in bp.get("roles", [])}
    for c in bp.get("categories", []):
        for item in [c] + c.get("channels", []):
            for k in ("private_to", "writers"):
                blueprint_role_names |= {str(x).lower() for x in item.get(k) or []}
    for item in bp.get("channels", []):
        for k in ("private_to", "writers"):
            blueprint_role_names |= {str(x).lower() for x in item.get(k) or []}
    blueprint_role_names.discard("@everyone")
    pending_posts: list = []
    pending_syncs: list = []
    order_groups: list = []  # (label, [ids in blueprint order])

    def lookup(name: str, tname: str, parent_id, was: str | None):
        fam = family(tname)
        names = [name] + ([was] if update and was else [])
        for nm in names:
            c = by_key.get((parent_id, fam, norm(nm, tname)))
            if c and c["id"] not in claimed:
                return c, nm != name
        if update:  # it may have moved to another category
            for nm in names:
                cands = [c for c in by_famname.get((fam, norm(nm, tname)), []) if c["id"] not in claimed]
                if len(cands) == 1:
                    return cands[0], nm != name
        return None, False

    def create_channel(body: dict, type_name: str) -> dict | None:
        want = type_name
        if not community and want in FALLBACK:
            want = FALLBACK[want]
            body["type"] = TYPES[want]
        try:
            return client.call("POST", f"/guilds/{gid}/channels", body)
        except DiscordError as e:
            if want in FALLBACK and e.status == 400:
                warn(f"{body['name']}: {want} channel not allowed here, creating as {FALLBACK[want]}")
                body["type"] = TYPES[FALLBACK[want]]
                return client.call("POST", f"/guilds/{gid}/channels", body)
            raise

    def post_starter(ch: dict, chan: dict) -> None:
        text = fill(ch.get("message", ""))
        if not text or chan["type"] in (2, 13):
            return
        try:
            if chan["type"] == 15:  # forum: the message becomes the first post
                title = ch.get("message_title", "Start here")
                res = client.call("POST", f"/channels/{chan['id']}/threads",
                                  {"name": title[:100], "message": {"content": split_message(text)[0]}})
                result["messages"][ch["name"]] = [res["id"]]
                counts["messages"] += 1
                return
            ids = []
            for chunk in split_message(text):
                m = client.call("POST", f"/channels/{chan['id']}/messages",
                                {"content": chunk, "allowed_mentions": {"parse": []}})
                ids.append(m["id"])
                counts["messages"] += 1
                time.sleep(0.3)
            result["messages"][ch["name"]] = ids
            if ch.get("pin") and ids:
                pin(chan["id"], ids[0])
        except DiscordError as e:
            warn(f"message in #{chan['name']} failed: {explain(e)}")

    def pin(cid: str, mid: str) -> None:
        try:
            client.call("PUT", f"/channels/{cid}/messages/pins/{mid}")
        except DiscordError:
            client.call("PUT", f"/channels/{cid}/pins/{mid}")

    def sync_starter(ch: dict, chan: dict) -> None:
        """--update: make the bot's starter post in an existing channel match the blueprint."""
        if not ch.get("message") or chan["type"] in (2, 13):
            return
        if chan["type"] == 15:
            note(f"#{chan['name']}: forum starter posts aren't edited - change that post in Discord")
            return
        try:
            msgs = client.call("GET", f"/channels/{chan['id']}/messages?limit=50") or []
        except DiscordError as e:
            warn(f"could not read #{chan['name']}: {explain(e)}")
            return
        mine = sorted([m for m in msgs if m.get("author", {}).get("id") == bot_id and m.get("type", 0) == 0],
                      key=lambda m: int(m["id"]))
        if not mine:
            out(f"  + #{chan['name']}: starter post{would}")
            counts["created"] += 1
            if not dry:
                post_starter(ch, chan)
            return
        chunks = split_message(fill(ch["message"]))
        if [m["content"] for m in mine[:len(chunks)]] == chunks:
            if ch.get("pin") and not mine[0].get("pinned") and not dry:
                pin(chan["id"], mine[0]["id"])
            return
        out(f"  ~ #{chan['name']}: starter post text{would}")
        counts["changed"] += 1
        if dry:
            return
        try:
            for m, chunk in zip(mine, chunks):
                if m["content"] != chunk:
                    client.call("PATCH", f"/channels/{chan['id']}/messages/{m['id']}",
                                {"content": chunk, "allowed_mentions": {"parse": []}})
                    time.sleep(0.3)
            for chunk in chunks[len(mine):]:
                client.call("POST", f"/channels/{chan['id']}/messages",
                            {"content": chunk, "allowed_mentions": {"parse": []}})
            if len(mine) > len(chunks):
                note(f"#{chan['name']}: the new post is shorter; {len(mine) - len(chunks)} older bot message(s) left in place")
        except DiscordError as e:
            warn(f"could not edit the post in #{chan['name']}: {explain(e)}")

    def changes_for(live: dict, item: dict, tname: str, parent_id, access: dict, renamed: bool):
        fam = family(tname)
        body, desc = {}, []
        if renamed or (live["name"] != item["name"] and norm(live["name"], tname) != norm(item["name"], tname)):
            body["name"] = item["name"]
            desc.append(f"rename from '{live['name']}'")
        if tname != "category" and live.get("parent_id") != parent_id:
            body["parent_id"] = parent_id
            desc.append("move to another category")
        if fam == "text" and tname != "category":
            if "topic" in item and (live.get("topic") or "") != fill(item["topic"]):
                body["topic"] = fill(item["topic"])
                desc.append("topic")
            if "slowmode" in item and int(live.get("rate_limit_per_user") or 0) != item["slowmode"]:
                body["rate_limit_per_user"] = item["slowmode"]
                desc.append(f"slowmode {item['slowmode']}s")
        if tname == "voice" and "user_limit" in item and int(live.get("user_limit") or 0) != int(item["user_limit"]):
            body["user_limit"] = int(item["user_limit"])
            desc.append(f"user limit {item['user_limit']}")
        desired = build_overwrites(access, gid, role_ids, bot_id, "voice" if fam == "voice" else "text", warn)
        # Only overwrites for @everyone, the bot and roles this blueprint talks about are ours to set;
        # anything else (other bots, hand-made exceptions) is kept as it is.
        managed = set(managed_targets) | {str(role_ids[n]) for n in blueprint_role_names
                                          if n in role_ids and not str(role_ids[n]).startswith("new:")}
        keep = [o for o in live.get("permission_overwrites", []) if str(o["id"]) not in managed]
        merged = keep + desired
        if ow_map(merged) != ow_map(live.get("permission_overwrites", [])):
            body["permission_overwrites"] = merged
            desc.append("who can see/post")
        return body, desc

    def handle_existing(live: dict, item: dict, tname: str, parent_id, access: dict, renamed: bool, indent: str, label: str):
        claimed.add(live["id"])
        if not update:
            out(f"{indent}= {label} (already exists)")
            counts["skipped"] += 1
            return
        body, desc = changes_for(live, item, tname, parent_id, access, renamed)
        if body:
            out(f"{indent}~ {label}: {', '.join(desc)}{would}")
            counts["changed"] += 1
            if not dry:
                try:
                    res = client.call("PATCH", f"/channels/{live['id']}", body)
                    live.update(res or {})
                    if "name" in body:
                        chan_ids[norm(item["name"], tname)] = live["id"]
                    time.sleep(0.3)
                except DiscordError as e:
                    warn(f"could not change {live['name']}: {explain(e)}")
        else:
            out(f"{indent}= {label} (no changes)")
            counts["skipped"] += 1
        if tname != "category":
            pending_syncs.append((item, live))

    def make(ch: dict, parent: dict | None, parent_id, parent_is_new: bool, group: list) -> None:
        tname = ch.get("type", "text")
        fam = family(tname)
        label = f"{ICON.get(tname, '#')} {ch['name']}"
        indent = "      " if parent else "  "
        access = merged_access(parent, ch)
        if not parent_is_new:
            live, renamed = lookup(ch["name"], tname, parent_id, ch.get("was"))
            if live:
                handle_existing(live, ch, tname, parent_id, access, renamed, indent, label)
                group.append((fam, live["id"]))
                return
        if dry:
            out(f"{indent}+ {label}{describe(access)} (would create" + (", +message)" if ch.get("message") else ")"))
            counts["created"] += 1
            return
        body = {"name": ch["name"], "type": TYPES[tname],
                "permission_overwrites": build_overwrites(access, gid, role_ids, bot_id, fam, warn)}
        if parent_id:
            body["parent_id"] = parent_id
        if fam == "text":
            if ch.get("topic"):
                body["topic"] = fill(ch["topic"])
            if ch.get("slowmode"):
                body["rate_limit_per_user"] = ch["slowmode"]
        if tname == "voice" and ch.get("user_limit"):
            body["user_limit"] = int(ch["user_limit"])
        try:
            created = create_channel(body, tname)
        except DiscordError as e:
            warn(f"could not create {ch['name']}: {explain(e)}")
            return
        out(f"{indent}+ {ICON.get(TYPE_NAMES.get(created['type'], 'text'), '#')} {created['name']}")
        result["channels"][ch["name"]] = created["id"]
        chan_ids.setdefault(norm(created["name"], TYPE_NAMES.get(created["type"], "text")), created["id"])
        group.append((fam, created["id"]))
        counts["created"] += 1
        time.sleep(0.3)
        pending_posts.append((ch, created))  # posted after every channel exists, so links resolve

    out("\nChannels:")
    top_group: list = []
    for ch in bp.get("channels", []):
        make(ch, None, None, False, [])
    for c in bp.get("categories", []):
        live, renamed = lookup(c["name"], "category", None, c.get("was"))
        group: list = []
        if live:
            handle_existing(live, c, "category", None, merged_access(None, c), renamed, "  ",
                            f"[{c['name']}]")
            cat_id, is_new = live["id"], False
            top_group.append(("category", cat_id))
        elif dry:
            cat_id, is_new = None, True
            out(f"  + [{c['name']}]{describe(merged_access(None, c))} (would create)")
            counts["created"] += 1
        else:
            body = {"name": c["name"], "type": 4,
                    "permission_overwrites": build_overwrites(merged_access(None, c), gid, role_ids, bot_id, "text", warn)}
            try:
                created = client.call("POST", f"/guilds/{gid}/channels", body)
            except DiscordError as e:
                warn(f"could not create category {c['name']}: {explain(e)} - skipping its channels")
                continue
            cat_id, is_new = created["id"], True
            result["channels"][c["name"]] = cat_id
            top_group.append(("category", cat_id))
            out(f"  + [{c['name']}]")
            counts["created"] += 1
            time.sleep(0.3)
        for ch in c.get("channels", []):
            make(ch, c, cat_id, is_new, group)
        order_groups.append((f"[{c['name']}]", group))
    order_groups.insert(0, ("categories", top_group))

    for ch, created in pending_posts:
        post_starter(ch, created)
    if update:
        out("\nStarter posts:") if pending_syncs else None
        for item, live in pending_syncs:
            sync_starter(item, live)

    # ------------------------------------------------------------------ order (update only)
    if update:
        live_now = existing_chans if dry else (client.call("GET", f"/guilds/{gid}/channels") or [])
        pos = {c["id"]: c["position"] for c in live_now}
        payload, moved = [], []
        for label, group in order_groups:
            for fam in ("category", "text", "voice"):
                ids = [i for f, i in group if f == fam and i in pos]
                if len(ids) < 2:
                    continue
                current = sorted(ids, key=lambda i: (pos[i], int(i)))
                if current != ids:
                    slots = sorted(pos[i] for i in ids)
                    if len(set(slots)) < len(slots):
                        slots = list(range(min(slots), min(slots) + len(ids)))
                    payload += [{"id": i, "position": p} for i, p in zip(ids, slots)]
                    moved.append(label)
        if payload:
            out(f"\n  ~ reorder channels in {', '.join(dict.fromkeys(moved))}{would}")
            counts["changed"] += 1
            if not dry:
                try:
                    client.call("PATCH", f"/guilds/{gid}/channels", payload)
                except DiscordError as e:
                    warn(f"could not reorder channels: {explain(e)}")
        roles_now = existing_roles if dry else (client.call("GET", f"/guilds/{gid}/roles") or [])
        rinfo = {r["id"]: r for r in roles_now}
        movable = [i for i in role_order if i in rinfo and not role_protection(rinfo[i], gid, s["bot_top"])]
        current = sorted(movable, key=lambda i: rank(rinfo[i]), reverse=True)
        slots = sorted((rinfo[i]["position"] for i in movable), reverse=True)
        if len(movable) > 1 and current != movable and (
                len(set(slots)) < len(slots) or max(slots) >= s["bot_top"][0]):
            # Shared position numbers (common on Discord) can't be reordered safely by number.
            note("roles aren't in blueprint order, and Discord gives several of them the same position number. "
                 "Drag them into order in Server Settings > Roles: " + " > ".join("@" + rinfo[i]["name"] for i in movable))
        elif len(movable) > 1 and current != movable:
            out(f"  ~ reorder roles: {' > '.join('@' + rinfo[i]['name'] for i in movable)}{would}")
            counts["changed"] += 1
            if not dry:
                try:
                    client.call("PATCH", f"/guilds/{gid}/roles",
                                [{"id": i, "position": p} for i, p in zip(movable, slots)])
                except DiscordError as e:
                    warn(f"could not reorder roles: {explain(e)}")

    # ------------------------------------------------------------------ remove (update + confirm only)
    rm = bp.get("remove") or {}
    if any(rm.values()):
        if not update:
            note("the blueprint's 'remove' list is ignored without --update")
        else:
            targets, refusals = resolve_delete(rm, s, gid)
            if targets or refusals:
                out("\nDelete (from the blueprint's remove list):")
            for _, _, label in targets:
                out(f"  - {label}")
            for r in refusals:
                note(r)
            if targets and (dry or not confirm):
                out("  Nothing deleted. Deleting can't be undone: show the user this list, and only after "
                    "they approve it re-run with --confirm-delete.")
            elif targets:
                done, probs = do_delete(client, gid, targets)
                counts["deleted"] += done
                for p in probs:
                    warn(p)

    verb = "Would create" if dry else "Created"
    summary = f"\n{verb} {counts['created']}"
    if update:
        summary += f", {'would change' if dry else 'changed'} {counts['changed']}"
        summary += f", deleted {counts['deleted']}" if counts["deleted"] else ""
    summary += f", unchanged/skipped {counts['skipped']}"
    summary += "" if dry else f", posted {counts['messages']} message(s)"
    out(summary + f", {len(problems)} problem(s)" + (f", {len(notes)} note(s)." if notes else "."))
    if not dry:
        log = Path(args.blueprint).with_suffix(".result.json")
        merged = {}
        if log.exists():
            try:
                merged = json.loads(log.read_text(encoding="utf-8"))
            except Exception:
                merged = {}
        if merged.get("guild_id") not in (None, gid):
            log = log.with_name(log.stem + f".{gid}.json")
            merged = {}
        merged["guild_id"] = gid
        for k in ("roles", "channels", "emojis", "stickers", "messages"):
            merged.setdefault(k, {}).update(result[k])
        merged["problems"] = problems
        log.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        out(f"Log saved to {log}")
    return 1 if problems else 0


def cmd_delete(args, client: Client | None = None) -> int:
    names = {"channels": args.channel or [], "roles": args.role or [],
             "emojis": args.emoji or [], "stickers": args.sticker or []}
    if not any(names.values()):
        sys.exit("Name at least one --channel, --role, --emoji or --sticker to delete.")
    client = client or Client(load_token(args.env_file))
    try:
        s = fetch_server(client, args.guild)
    except DiscordError as e:
        out(explain(e))
        return 1
    targets, refusals = resolve_delete(names, s, args.guild)
    out(f"Server: {s['guild']['name']}")
    if targets:
        out("Will delete:" if args.confirm_delete else "Would delete:")
        for _, _, label in targets:
            out(f"  - {label}")
    for r in refusals:
        out(f"  x {r}")
    if not targets:
        return 1 if refusals else 0
    if not args.confirm_delete:
        out("\nNothing deleted. Deleting can't be undone (messages inside deleted channels are lost). "
            "Re-run with --confirm-delete only after the user has approved this exact list.")
        return 0
    done, problems = do_delete(client, args.guild, targets)
    for p in problems:
        out(f"   ! {p}")
    out(f"\nDeleted {done}, {len(problems)} problem(s).")
    return 1 if problems or refusals else 0


def cmd_undo(args, client: Client | None = None) -> int:
    """Delete exactly what earlier applies created, using the .result.json log."""
    try:
        log = json.loads(Path(args.result).read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"Log not found: {args.result}")
    gid = log.get("guild_id")
    if args.guild and args.guild != gid:
        sys.exit(f"That log belongs to server {gid}, not {args.guild}.")
    client = client or Client(load_token(args.env_file))
    dry = args.dry_run
    try:
        guild = client.call("GET", f"/guilds/{gid}")
        live_chans = {c["id"]: c for c in client.call("GET", f"/guilds/{gid}/channels")}
        live_roles = {r["id"]: r for r in client.call("GET", f"/guilds/{gid}/roles")}
        live_emojis = {e["id"]: e for e in (client.call("GET", f"/guilds/{gid}/emojis") or [])}
        live_stickers = {x["id"]: x for x in (client.call("GET", f"/guilds/{gid}/stickers") or [])}
    except DiscordError as e:
        out(explain(e))
        return 1
    out(("DRY RUN - nothing will be deleted. " if dry else "") + f"Server: {guild['name']}")
    targets, gone = [], 0
    # Channels were logged parent-first, so reverse order removes children before categories.
    for name, cid in reversed(list(log.get("channels", {}).items())):
        if cid in live_chans:
            targets.append(("channel", cid, live_chans[cid]["name"]))
        else:
            gone += 1
    for kind, key, live in (("role", "roles", live_roles), ("emoji", "emojis", live_emojis),
                            ("sticker", "stickers", live_stickers)):
        for name, xid in log.get(key, {}).items():
            if xid in live:
                targets.append((kind, xid, ("@" if kind == "role" else f"{kind} ") + name))
            else:
                gone += 1
    for _, _, label in targets:
        out(f"  - {label}" + (" (would delete)" if dry else ""))
    problems: list[str] = []
    done = len(targets)
    if not dry:
        done, problems = do_delete(client, gid, targets)
    for p in problems:
        out(f"   ! {p}")
    out(f"\n{'Would delete' if dry else 'Deleted'} {done}, {gone} already gone, {len(problems)} problem(s).")
    if not dry and not problems:
        Path(args.result).rename(Path(args.result).with_suffix(".undone.json"))
    return 1 if problems else 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Build and maintain a Discord server from a JSON blueprint.")
    ap.add_argument("--env-file", help="path to a .env file holding DISCORD_BOT_TOKEN")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check a blueprint offline")
    v.add_argument("blueprint")
    sub.add_parser("check", help="test the token and list the bot's servers")
    i = sub.add_parser("inspect", help="show a server's roles, channels, emojis and stickers")
    i.add_argument("--guild", required=True)
    a = sub.add_parser("apply", help="create what is missing (and with --update, change what differs)")
    a.add_argument("blueprint")
    a.add_argument("--guild", required=True)
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--update", action="store_true", help="also change existing items to match")
    a.add_argument("--confirm-delete", action="store_true", help="with --update: delete what 'remove' lists")
    d = sub.add_parser("delete", help="delete named channels/roles/emojis/stickers")
    d.add_argument("--guild", required=True)
    d.add_argument("--channel", action="append")
    d.add_argument("--role", action="append")
    d.add_argument("--emoji", action="append")
    d.add_argument("--sticker", action="append")
    d.add_argument("--confirm-delete", action="store_true")
    u = sub.add_parser("undo", help="delete what earlier applies created, from the .result.json log")
    u.add_argument("result")
    u.add_argument("--guild")
    u.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return {"validate": cmd_validate, "check": cmd_check, "inspect": cmd_inspect, "apply": cmd_apply,
            "delete": cmd_delete, "undo": cmd_undo}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
