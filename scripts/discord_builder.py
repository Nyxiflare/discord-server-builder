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
  delete --guild ID [--channel N] [--role N] [--emoji N] [--sticker N] [--automod N] [--confirm-delete]
                                      delete named items; without --confirm-delete it only lists them
  undo RESULT.json [--dry-run]        delete exactly what earlier applies created
  health [BLUEPRINT] [--guild ID]     score a planned layout or a live server 0-100, with fixes
  export --guild ID OUT.json          turn a live server into a clean, shareable blueprint (no IDs)
  preview BLUEPRINT [--out FILE]      write a Discord-style HTML mockup (no network requests)

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
import urllib.parse
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
ACCESS_KEYS = ("private_to", "read_only", "writers", "thread_only", "thread_staff", "media_to")
ROLE_LIST_KEYS = ("private_to", "writers", "thread_staff", "media_to")

# Expression slots by server boost level (premium_tier).
EMOJI_SLOTS = {0: 50, 1: 100, 2: 150, 3: 250}   # each for static and for animated
STICKER_SLOTS = {0: 5, 1: 15, 2: 30, 3: 60}
EMOJI_MAX_BYTES = 256 * 1024
STICKER_MAX_BYTES = 512 * 1024
MIME = {"png": "image/png", "gif": "image/gif", "jpeg": "image/jpeg", "webp": "image/webp",
        "lottie": "application/json"}
EMOJI_NAME = re.compile(r"^[A-Za-z0-9_]{2,32}$")

# ---- AutoMod (Discord's built-in filter; runs without any bot online)
AM_KEYWORD, AM_SPAM, AM_PRESET, AM_MENTION = 1, 3, 4, 5
AM_CAPS = {AM_KEYWORD: 6, AM_SPAM: 1, AM_PRESET: 1, AM_MENTION: 1, 6: 1}   # rules allowed per server, by trigger
AM_TRIGGER_NAMES = {1: "keyword", 3: "spam", 4: "preset (slurs/profanity)", 5: "mention spam", 6: "member profile"}
AM_PREFIX = "SB · "          # names of rules this tool manages
AM_PRESET_PROFANITY, AM_PRESET_SEXUAL, AM_PRESET_SLURS = 1, 2, 3
AM_LEVELS = {
    "family-friendly": {"presets": [1, 2, 3], "mentions": 5, "block_invites": True, "block_links": True, "timeout": 3600},
    "standard": {"presets": [2, 3], "mentions": 8, "block_invites": True, "block_links": False, "timeout": 3600},
    "relaxed": {"presets": [3], "mentions": 15, "block_invites": False, "block_links": False, "timeout": 0},
}
# Phrases common in Discord scams and spam (keyword rules match whole words; * is a wildcard).
AM_SCAM_WORDS = [
    "free nitro", "nitro giveaway", "free discord nitro", "steam gift", "claim your reward", "claim your prize",
    "airdrop", "double your crypto", "guaranteed profit", "investment opportunity", "dm me for collab",
    "dm me to collab", "dm for promo", "promo for promo", "sub4sub", "follow for follow", "check my bio",
    "whatsapp me", "telegram me",
]
AM_SCAM_REGEX = [
    r"(?i)\b(?:dlscord|disc0rd|discorcl|dicsord|discrod|discord-?(?:gift|nitro|airdrop)s?)\.[a-z]{2,}",
    r"(?i)\b(?:stearn|steamcommunlty|steamcomunity|steam-?gifts?)\.[a-z]{2,}",
    r"(?i)(?:crypto|token|nft|coin)\s*(?:air\s?drop|give\s?away)",
]
AM_INVITE_REGEX = r"(?i)(?:discord\.gg|discord(?:app)?\.com/invite)/[a-z0-9-]+"
AM_LINK_REGEX = r"(?i)https?://\S+"
AM_DEFAULT_ALLOWED_LINKS = ["youtube.com", "youtu.be", "twitch.tv", "tiktok.com", "instagram.com", "x.com",
                            "twitter.com", "kick.com", "spotify.com", "github.com"]

# ---- system channel flags (guild join/boost messages)
SYS_SUPPRESS_JOIN, SYS_SUPPRESS_BOOST, SYS_SUPPRESS_TIPS, SYS_SUPPRESS_JOIN_REPLIES = 1, 2, 4, 8


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
                errors.append(f"Role '{n}' grants ADMINISTRATOR. Blueprints can be shared, so they never grant it: "
                              "use the 'admin' preset, and give Administrator to your own role by hand in Discord.")
        else:
            errors.append(f"Role '{n}': permissions must be a preset name or a list.")
        if "color" in r:
            try:
                parse_color(r["color"])
            except ValueError as e:
                errors.append(f"Role '{n}': {e}")

    def check_access(where: str, a: dict) -> None:
        if a.get("thread_staff") and not a.get("thread_only"):
            warnings.append(f"{where}: 'thread_staff' has no effect unless thread_only is true.")
        for key in ROLE_LIST_KEYS:
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
        if ch.get("reactions"):
            if not isinstance(ch["reactions"], list) or len(ch["reactions"]) > 20:
                errors.append(f"{where}/{n}: 'reactions' must be a list of up to 20 emojis.")
            elif not ch.get("message"):
                warnings.append(f"{where}/{n}: 'reactions' need a starter 'message' to react to.")
        if ch.get("thread_only") and t not in ("text", "announcement"):
            errors.append(f"{where}/{n}: thread_only (private-thread tickets) only works on text channels.")
        all_channel_names.add(norm(n, "text"))
        check_access(f"{where}/{n}", ch)

    total = 0
    all_channel_names: set[str] = set()
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

    def known_channel(n: str) -> bool:
        t = norm(str(n), "text")
        return t in all_channel_names or any(c.endswith(t) and not c[-len(t) - 1].isalnum()
                                             for c in all_channel_names if len(c) > len(t))

    am = bp.get("automod")
    if am is not None:
        if not isinstance(am, dict):
            errors.append("'automod' must be an object like {\"level\": \"standard\", \"alert_channel\": \"mod-log\"}.")
        else:
            if am.get("level", "standard") not in AM_LEVELS:
                errors.append(f"automod.level must be one of {', '.join(AM_LEVELS)}.")
            for k in ("blocked_words", "allowed_words", "scam_words", "allowed_links", "exempt_roles", "exempt_channels"):
                if k in am and not isinstance(am[k], list):
                    errors.append(f"automod.{k} must be a list.")
            if len(am.get("blocked_words", [])) > 1000:
                errors.append("automod.blocked_words: Discord allows 1000 words per rule.")
            if len(am.get("allowed_words", [])) > 100:
                errors.append("automod.allowed_words: Discord allows 100 per rule.")
            long = [w for w in am.get("blocked_words", []) + am.get("allowed_words", []) if len(str(w)) > 60]
            if long:
                errors.append(f"automod words must be 60 characters or less: {long[:2]}")
            if len(am.get("block_message", "")) > 150:
                errors.append("automod.block_message must be 150 characters or less.")
            for rn in am.get("exempt_roles", []):
                if str(rn).lower() not in role_names:
                    warnings.append(f"automod: exempt role '{rn}' is not in this blueprint (fine if it already exists).")
            for cn in am.get("exempt_channels", []) + ([am["alert_channel"]] if am.get("alert_channel") else []):
                if not known_channel(cn):
                    warnings.append(f"automod: channel '{cn}' is not in this blueprint (fine if it already exists).")

    wl = bp.get("welcome")
    if wl is not None:
        if not isinstance(wl, dict):
            errors.append("'welcome' must be an object.")
        else:
            if wl.get("system_channel") and not known_channel(wl["system_channel"]):
                warnings.append(f"welcome.system_channel '{wl['system_channel']}' is not in this blueprint (fine if it already exists).")
            scr = wl.get("screen") or {}
            if len(scr.get("description", "")) > 140:
                errors.append("welcome.screen.description must be 140 characters or less.")
            chans = scr.get("channels", [])
            if len(chans) > 5:
                errors.append("welcome.screen.channels: Discord shows at most 5.")
            for wc in chans:
                if not wc.get("channel") or not wc.get("description"):
                    errors.append("welcome.screen.channels entries need 'channel' and 'description'.")
                elif len(wc["description"]) > 50:
                    errors.append(f"welcome screen description for '{wc['channel']}' must be 50 characters or less.")
            if scr:
                warnings.append("The welcome screen only works once Community is enabled; it is skipped otherwise.")

    ob = bp.get("onboarding")
    if ob is not None:
        if not isinstance(ob, dict):
            errors.append("'onboarding' must be an object.")
        else:
            qs = ob.get("questions", [])
            if len(qs) > 15:
                errors.append("onboarding: at most 15 questions.")
            for q in qs:
                if not q.get("title"):
                    errors.append("onboarding: every question needs a 'title'.")
                opts = q.get("options", [])
                if not 1 <= len(opts) <= 50:
                    errors.append(f"onboarding question '{q.get('title')}': needs 1-50 options.")
                for o in opts:
                    if not o.get("title"):
                        errors.append(f"onboarding question '{q.get('title')}': an option has no title.")
                    if not o.get("roles") and not o.get("channels"):
                        errors.append(f"onboarding option '{o.get('title')}': give it 'roles' and/or 'channels' to assign.")
                    for rn in o.get("roles", []):
                        if str(rn).lower() not in role_names:
                            warnings.append(f"onboarding option '{o.get('title')}': role '{rn}' is not in this blueprint.")
            if ob.get("enable", True) and len(ob.get("default_channels", [])) < 7:
                warnings.append("onboarding: Discord needs at least 7 default channels to turn onboarding on; "
                                "with fewer, the questions are saved but onboarding stays off.")
            warnings.append("Onboarding only works once Community is enabled; it is skipped otherwise.")

    # ---- shared blueprints are untrusted input
    for kind, items in (("emoji", bp.get("emojis", [])), ("sticker", bp.get("stickers", []))):
        for it in items:
            f = str(it.get("file", ""))
            target = (base / f).resolve() if f else None
            if f and (Path(f).is_absolute() or ".." in Path(f).parts or (target and base not in target.parents)):
                errors.append(f"{kind} '{it.get('name')}': file must be inside the blueprint's folder (got {f!r}).")
    texts = []
    for c in bp.get("categories", []):
        for ch in c.get("channels", []):
            texts += [ch.get("message", ""), ch.get("topic", "")]
    for ch in bp.get("channels", []):
        texts += [ch.get("message", ""), ch.get("topic", "")]
    texts += [str(((bp.get("welcome") or {}).get("screen") or {}).get("description", "")),
              str((bp.get("automod") or {}).get("block_message", ""))]
    blob = "\n".join(t for t in texts if t)
    invites = sorted(set(re.findall(r"(?i)(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+", blob)))
    if invites:
        warnings.append(f"Starter posts contain Discord invite links ({', '.join(invites[:3])}). Check they're yours before applying.")
    hosts = sorted(set(h.lower() for h in re.findall(r"https?://([^/\s)>\]]+)", blob)))
    if hosts:
        warnings.append(f"Starter posts link to: {', '.join(hosts[:8])}. Check every link before applying a shared blueprint.")
    if re.search(r"@(everyone|here)\b", blob):
        warnings.append("Starter posts mention @everyone/@here as text; the bot never pings, but check the wording.")

    lang = bp.get("language")
    if lang is not None and not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})*", str(lang)):
        errors.append(f"language '{lang}' should be a code like es, pt-BR, hi, ja, ar.")
    stripped = set("!\"#$%&'()*+,./:;<=>?@[\\]^`{|}~")
    for c in bp.get("categories", []):
        for ch in c.get("channels", []):
            if family(ch.get("type", "text")) == "text":
                bad = sorted({x for x in ch.get("name", "") if x in stripped})
                if bad:
                    warnings.append(f"{c['name']}/{ch['name']}: Discord removes {' '.join(bad)} from text channel names.")

    rm = bp.get("remove")
    if rm is not None:
        if not isinstance(rm, dict) or any(k not in ("channels", "roles", "emojis", "stickers", "automod") for k in rm):
            errors.append("'remove' must look like {\"channels\": [...], \"roles\": [...], \"emojis\": [...], \"stickers\": [...], \"automod\": [...]}.")
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
    if a.get("thread_only"):
        st = a.get("thread_staff") or []
        parts.append("private-thread tickets" + (f", seen by {', '.join(st)}" if st else ""))
    if a.get("media_to"):
        parts.append("images/links: " + ", ".join(a["media_to"]))
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
    am = bp.get("automod")
    if am:
        out(f"\nAutoMod ({am.get('level', 'standard')}):")
        for r in automod_rules(am, lambda n: f"#{n}", {k.lower(): "x" for k in am.get("exempt_roles", [])}, lambda m: None):
            extra = ""
            if r["trigger_type"] == AM_KEYWORD:
                md = r["trigger_metadata"]
                extra = f" ({len(md.get('keyword_filter', []))} phrases, {len(md.get('regex_patterns', []))} patterns)"
            acts = {1: "block", 2: "alert", 3: "timeout"}
            out(f"  {r['name'][len(AM_PREFIX):]}{extra} -> {' + '.join(acts[a['type']] for a in r['actions'])}")
    wl = bp.get("welcome")
    if wl:
        out("\nWelcome:")
        if wl.get("system_channel"):
            out(f"  join messages in #{wl['system_channel']}")
        if (wl.get("screen") or {}).get("channels"):
            out("  welcome screen: " + ", ".join("#" + c["channel"] for c in wl["screen"]["channels"]))
    ob = bp.get("onboarding")
    if ob:
        out("\nOnboarding questions:")
        for q in ob.get("questions", []):
            out(f"  {q['title']}: " + ", ".join(o["title"] for o in q.get("options", [])))
    rm = bp.get("remove") or {}
    if any(rm.values()):
        out("\nTo delete (needs --update --confirm-delete):")
        for k, v in rm.items():
            for n in v:
                out(f"  - {k[:-1]}: {n}")


# --------------------------------------------------------------------------- automod / onboarding helpers

def automod_rules(cfg: dict, channel_id, role_ids: dict, warn) -> list[dict]:
    """Turn the blueprint's "automod" block into Discord AutoMod rule bodies (named with AM_PREFIX)."""
    level = AM_LEVELS[cfg.get("level", "standard")]
    alert = channel_id(cfg["alert_channel"]) if cfg.get("alert_channel") else None
    if cfg.get("alert_channel") and not alert:
        warn(f"AutoMod alert channel '{cfg['alert_channel']}' not found - rules will block without alerting")
    exempt_roles = []
    for rn in cfg.get("exempt_roles", []):
        rid = role_ids.get(str(rn).lower())
        if rid and not str(rid).startswith("new:"):
            exempt_roles.append(str(rid))
    exempt_channels = [c for c in (channel_id(n) for n in cfg.get("exempt_channels", [])) if c]
    allowed = [w for w in cfg.get("allowed_words", []) if w][:100]
    msg = (cfg.get("block_message") or "This message was blocked by the server's filter. If that's a mistake, ask a moderator.")[:150]

    def actions(timeout: int = 0) -> list:
        acts = [{"type": 1, "metadata": {"custom_message": msg}}]
        if alert:
            acts.append({"type": 2, "metadata": {"channel_id": alert}})
        if timeout:
            acts.append({"type": 3, "metadata": {"duration_seconds": timeout}})
        return acts

    def rule(name, trigger, metadata, acts):
        return {"name": AM_PREFIX + name, "event_type": 1, "trigger_type": trigger,
                "trigger_metadata": metadata, "actions": acts, "enabled": True,
                "exempt_roles": exempt_roles[:20], "exempt_channels": exempt_channels[:50]}

    rules = [rule("Slurs & adult content", AM_PRESET,
                  {"presets": level["presets"], "allow_list": allowed}, actions())]
    regex = list(AM_SCAM_REGEX)
    scam_allow = list(allowed)
    if cfg.get("block_invites", level["block_invites"]):
        regex.append(AM_INVITE_REGEX)
    if cfg.get("block_links", level["block_links"]):
        regex.append(AM_LINK_REGEX)
        scam_allow += cfg.get("allowed_links", AM_DEFAULT_ALLOWED_LINKS)
    words = AM_SCAM_WORDS + [w for w in cfg.get("scam_words", []) if w]
    rules.append(rule("Scams, invites & spam links", AM_KEYWORD,
                      {"keyword_filter": [w[:60] for w in words][:1000], "regex_patterns": regex[:10],
                       "allow_list": [w[:60] for w in scam_allow][:100]}, actions(level["timeout"])))
    blocked = [w[:60] for w in cfg.get("blocked_words", []) if w]
    if blocked:
        rules.append(rule("Blocked words", AM_KEYWORD,
                          {"keyword_filter": blocked[:1000], "allow_list": allowed}, actions()))
    rules.append(rule("Mention spam", AM_MENTION,
                      {"mention_total_limit": int(cfg.get("max_mentions", level["mentions"])),
                       "mention_raid_protection_enabled": True}, actions(600)))
    rules.append(rule("Spam", AM_SPAM, {}, actions()))
    return rules


def _norm_rule(r: dict) -> dict:
    """Comparable view of an AutoMod rule (Discord adds extra fields and reorders lists)."""
    md = r.get("trigger_metadata") or {}
    keep = {k: (sorted(v) if isinstance(v, list) else v) for k, v in md.items()
            if k in ("keyword_filter", "regex_patterns", "allow_list", "presets", "mention_total_limit",
                     "mention_raid_protection_enabled") and v not in (None, [], False)}
    acts = sorted(json.dumps({"type": a["type"], "metadata": {k: v for k, v in (a.get("metadata") or {}).items() if v}},
                             sort_keys=True) for a in r.get("actions", []))
    return {"md": keep, "actions": acts, "enabled": bool(r.get("enabled", True)),
            "roles": sorted(map(str, r.get("exempt_roles", []))), "channels": sorted(map(str, r.get("exempt_channels", [])))}


_SNOW = [0]


def new_snowflake() -> str:
    """Discord wants ids on new onboarding prompts/options; any unused snowflake-shaped number works."""
    _SNOW[0] = (_SNOW[0] + 1) % 4096
    return str(((int(time.time() * 1000) - 1420070400000) << 22) | (os.getpid() % 1024) << 12 | _SNOW[0])


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
        "automod": [],
    }
    try:
        s["automod"] = client.call("GET", f"/guilds/{gid}/auto-moderation/rules") or []
    except DiscordError:
        s["automod"] = []  # needs Manage Server; the AutoMod step reports it if it matters
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
    out("AutoMod rules: " + (", ".join(f"{r['name']} ({AM_TRIGGER_NAMES.get(r['trigger_type'], '?')})"
                                       for r in s["automod"]) or "none"))
    sysc = guild.get("system_channel_id")
    sysname = next((c["name"] for c in chans if c["id"] == sysc), None)
    out(f"Join messages: {'#' + sysname if sysname else 'off'}")
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
    if access.get("thread_only") and fam != "voice":
        # Ticket channel without a bot: members can't chat here, but each can open a PRIVATE thread
        # that only they, people they add, and roles with Manage Threads (staff) can see.
        add(guild_id, 0, allow=perm("CREATE_PRIVATE_THREADS", "SEND_MESSAGES_IN_THREADS", "READ_MESSAGE_HISTORY"),
            deny=perm("SEND_MESSAGES", "CREATE_PUBLIC_THREADS"))
        for rn in access.get("thread_staff") or []:
            if (r := rid(rn)):
                add(r, 0, allow=perm("VIEW_CHANNEL", "SEND_MESSAGES", "MANAGE_THREADS", "SEND_MESSAGES_IN_THREADS"))
    if access.get("media_to") and fam != "voice":
        # Images and link previews only for these roles (e.g. level 2+): cuts spam from brand-new accounts.
        media = perm("ATTACH_FILES", "EMBED_LINKS")
        add(guild_id, 0, deny=media)
        for rn in access["media_to"]:
            if (r := rid(rn)):
                add(r, 0, allow=media)
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
    for n in names.get("automod", []):
        hits = [r for r in s.get("automod", []) if r["name"].lower() in (n.strip().lower(), (AM_PREFIX + n.strip()).lower())]
        if not hits:
            refusals.append(f"AutoMod rule '{n}': not found")
        else:
            targets.append(("automod", hits[0]["id"], f"AutoMod rule {hits[0]['name']}"))
    order = {"channel": 0, "category": 1, "role": 2, "emoji": 3, "sticker": 4, "automod": 5}
    targets.sort(key=lambda t: order[t[0]])
    return targets, refusals


def do_delete(client: Client, gid: str, targets: list):
    done, problems = 0, []
    for kind, tid, label in targets:
        path = {"channel": f"/channels/{tid}", "category": f"/channels/{tid}",
                "role": f"/guilds/{gid}/roles/{tid}", "emoji": f"/guilds/{gid}/emojis/{tid}",
                "sticker": f"/guilds/{gid}/stickers/{tid}",
                "automod": f"/guilds/{gid}/auto-moderation/rules/{tid}"}[kind]
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
    result = {"guild_id": gid, "roles": {}, "channels": {}, "emojis": {}, "stickers": {}, "messages": {}, "automod": {}}
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
            for k in ROLE_LIST_KEYS:
                blueprint_role_names |= {str(x).lower() for x in item.get(k) or []}
    for item in bp.get("channels", []):
        for k in ROLE_LIST_KEYS:
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
            if ids:
                react(ch, chan["id"], ids[0], [])
        except DiscordError as e:
            warn(f"message in #{chan['name']} failed: {explain(e)}")

    def react(ch: dict, cid: str, mid: str, existing: list) -> None:
        """Add the blueprint's reactions (e.g. for a reaction-role bot to use) to the starter post."""
        have = {(r.get("emoji") or {}).get("name") for r in existing if r.get("me")}
        for raw in ch.get("reactions", []):
            m = re.fullmatch(r"\{:([A-Za-z0-9_]{2,32}):\}", str(raw).strip())
            if m:
                e = emoji_by_name.get(m.group(1).lower())
                if not e or str(e.get("id", "")).startswith("new:"):
                    warn(f"#{ch['name']}: emoji :{m.group(1)}: not found - reaction skipped")
                    continue
                name, code = e["name"], f"{e['name']}:{e['id']}"
            else:
                name = code = str(raw).strip()
            if name in have:
                continue
            try:
                client.call("PUT", f"/channels/{cid}/messages/{mid}/reactions/{urllib.parse.quote(code)}/@me")
                time.sleep(0.3)
            except DiscordError as e:
                warn(f"#{ch['name']}: could not add reaction {raw}: {explain(e)}")

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
        if not dry and ch.get("reactions"):
            react(ch, chan["id"], mine[0]["id"], mine[0].get("reactions", []))
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

    planned = {norm(ch["name"], "text") for c in bp.get("categories", []) for ch in c.get("channels", [])}
    planned |= {norm(ch["name"], "text") for ch in bp.get("channels", [])}

    def chan_ref(name: str):
        """Channel id for a name; in a dry run, a placeholder for channels this run would create."""
        cid = find_channel(name)
        if cid:
            return cid
        t = norm(name, "text")
        if dry and (t in planned or any(p.endswith(t) and not p[-len(t) - 1].isalnum() for p in planned if len(p) > len(t))):
            return f"new:{name}"
        return None

    def emoji_fields(raw) -> dict:
        e = str(raw or "").strip()
        m = re.fullmatch(r"\{:([A-Za-z0-9_]{2,32}):\}", e)
        if m:
            live = emoji_by_name.get(m.group(1).lower())
            if live and not str(live.get("id", "")).startswith("new:"):
                return {"emoji_id": live["id"], "emoji_name": live["name"], "emoji_animated": bool(live.get("animated"))}
            return {}
        return {"emoji_name": e} if e else {}

    # ------------------------------------------------------------------ AutoMod
    am = bp.get("automod")
    if am:
        out(f"\nAutoMod ({am.get('level', 'standard')}):")
        live_rules = {r["name"].lower(): r for r in s["automod"]}
        per_type: dict[int, int] = {}
        for r in s["automod"]:
            per_type[r["trigger_type"]] = per_type.get(r["trigger_type"], 0) + 1
        for d in automod_rules(am, chan_ref, role_ids, warn):
            label = d["name"]
            live = live_rules.get(label.lower())
            if live:
                if not update:
                    out(f"  = {label} (already exists)")
                    counts["skipped"] += 1
                elif live["trigger_type"] != d["trigger_type"]:
                    note(f"{label}: Discord can't change a rule's type - remove it and re-run")
                elif _norm_rule(live) == _norm_rule(d):
                    out(f"  = {label} (no changes)")
                    counts["skipped"] += 1
                else:
                    out(f"  ~ {label}: filter settings{would}")
                    counts["changed"] += 1
                    if not dry:
                        body = {k: d[k] for k in ("trigger_metadata", "actions", "enabled", "exempt_roles", "exempt_channels")}
                        try:
                            client.call("PATCH", f"/guilds/{gid}/auto-moderation/rules/{live['id']}", body)
                        except DiscordError as e:
                            warn(f"could not change AutoMod rule {label}: {explain(e)}")
                continue
            t = d["trigger_type"]
            cap = AM_CAPS[t]
            if per_type.get(t, 0) >= cap:
                others = [r["name"] for r in s["automod"] if r["trigger_type"] == t]
                warn(f"{label} skipped - Discord allows {cap} {AM_TRIGGER_NAMES[t]} rule(s) and the server already has "
                     f"{', '.join(repr(o) for o in others)}. Edit or delete that one in Server Settings > AutoMod, then re-run.")
                continue
            per_type[t] = per_type.get(t, 0) + 1
            out(f"  + {label}" + (" (would create)" if dry else ""))
            counts["created"] += 1
            if dry:
                continue
            try:
                res = client.call("POST", f"/guilds/{gid}/auto-moderation/rules", d)
                result["automod"][label] = res["id"]
                time.sleep(0.3)
            except DiscordError as e:
                warn(f"could not create AutoMod rule {label}: {explain(e)}")

    # ------------------------------------------------------------------ welcome (join messages + welcome screen)
    wl = bp.get("welcome")
    if wl:
        out("\nWelcome:")
        sys_keys = (("join_messages", SYS_SUPPRESS_JOIN), ("boost_messages", SYS_SUPPRESS_BOOST),
                    ("setup_tips", SYS_SUPPRESS_TIPS), ("join_sticker_replies", SYS_SUPPRESS_JOIN_REPLIES))
        if wl.get("system_channel") or any(k in wl for k, _ in sys_keys):
            cur_cid = guild.get("system_channel_id")
            cur_flags = int(guild.get("system_channel_flags") or 0)
            want_cid = cur_cid
            if wl.get("system_channel"):
                want_cid = chan_ref(wl["system_channel"])
                if not want_cid:
                    warn(f"join-message channel '{wl['system_channel']}' not found")
                    want_cid = cur_cid
            flags = cur_flags
            for key, bit in sys_keys:
                if key in wl:
                    flags = (flags & ~bit) if wl[key] else (flags | bit)
            body = {}
            if want_cid != cur_cid:
                body["system_channel_id"] = want_cid
            if flags != cur_flags:
                body["system_channel_flags"] = flags
            if not body:
                out("  = join-message settings (no changes)")
                counts["skipped"] += 1
            elif cur_cid and not update and "system_channel_id" in body:
                note(f"join messages already go to another channel; run with --update to move them to #{wl['system_channel']}")
            else:
                out(f"  ~ join messages" + (f" -> #{wl['system_channel']}" if "system_channel_id" in body else "")
                    + (" (settings)" if "system_channel_flags" in body else "") + would)
                counts["changed"] += 1
                if not dry:
                    try:
                        client.call("PATCH", f"/guilds/{gid}", body)
                    except DiscordError as e:
                        warn(f"could not change join-message settings: {explain(e)}")
        scr = wl.get("screen")
        if scr:
            if not community:
                note("welcome screen skipped - turn on Community (Server Settings > Enable Community), then run apply --update")
            else:
                try:
                    current = client.call("GET", f"/guilds/{gid}/welcome-screen") or {}
                except DiscordError:
                    current = {}
                wcs = []
                for wc in scr.get("channels", []):
                    cid = chan_ref(wc["channel"])
                    if not cid:
                        warn(f"welcome screen: channel '{wc['channel']}' not found")
                        continue
                    wcs.append({"channel_id": cid, "description": wc["description"][:50],
                                **{"emoji_id": None, "emoji_name": None}, **emoji_fields(wc.get("emoji"))})
                body = {"enabled": True, "description": scr.get("description", ""), "welcome_channels": wcs}
                view = lambda ws: [(str(w.get("channel_id")), w.get("description"), w.get("emoji_name"), str(w.get("emoji_id") or ""))
                                   for w in ws]
                same = (current.get("description") or "") == body["description"] and \
                    view(current.get("welcome_channels", [])) == [(c, d, n, str(i or "")) for c, d, n, i in
                                                                  [(w["channel_id"], w["description"], w["emoji_name"], w["emoji_id"]) for w in wcs]]
                if same:
                    out("  = welcome screen (no changes)")
                    counts["skipped"] += 1
                elif current.get("welcome_channels") and not update:
                    note("the server already has a welcome screen; run with --update to replace it")
                else:
                    out(f"  ~ welcome screen: {len(wcs)} channel(s){would}")
                    counts["changed"] += 1
                    if not dry:
                        try:
                            client.call("PATCH", f"/guilds/{gid}/welcome-screen", body)
                        except DiscordError as e:
                            warn(f"could not set the welcome screen: {explain(e)}")

    # ------------------------------------------------------------------ onboarding (native self-roles)
    ob = bp.get("onboarding")
    if ob:
        out("\nOnboarding:")
        if not community:
            note("onboarding skipped - turn on Community first, then run apply --update. "
                 "Until then, use a reaction-role bot for self-assign roles.")
        else:
            try:
                cur = client.call("GET", f"/guilds/{gid}/onboarding") or {}
            except DiscordError as e:
                warn(f"could not read onboarding: {explain(e)}")
                cur = None
            if cur is not None:
                old_prompts = {p["title"].lower(): p for p in cur.get("prompts", [])}
                prompts = []
                for q in ob.get("questions", []):
                    oldp = old_prompts.get(q["title"].lower()) or {}
                    oldopts = {o["title"].lower(): o for o in oldp.get("options", [])}
                    opts = []
                    for o in q.get("options", []):
                        rids = []
                        for rn in o.get("roles", []):
                            rid = role_ids.get(str(rn).lower())
                            if rid and not str(rid).startswith("new:"):
                                rids.append(str(rid))
                            elif not dry:
                                warn(f"onboarding option '{o['title']}': role '{rn}' not found")
                        cids = [c for c in (chan_ref(x) for x in o.get("channels", [])) if c]
                        opts.append({"id": (oldopts.get(o["title"].lower()) or {}).get("id") or new_snowflake(),
                                     "title": o["title"], "description": o.get("description", ""),
                                     "role_ids": rids, "channel_ids": cids, **emoji_fields(o.get("emoji"))})
                    prompts.append({"id": oldp.get("id") or new_snowflake(), "type": 1 if q.get("dropdown") else 0,
                                    "title": q["title"], "single_select": bool(q.get("single_select")),
                                    "required": bool(q.get("required")), "in_onboarding": True, "options": opts})
                defaults = [c for c in (chan_ref(x) for x in ob.get("default_channels", [])) if c]
                want_on = bool(ob.get("enable", True)) and len(defaults) >= 7
                if ob.get("enable", True) and len(defaults) < 7:
                    note(f"onboarding needs 7+ default channels to switch on (has {len(defaults)}); questions are saved, onboarding stays off")
                body = {"prompts": prompts, "default_channel_ids": defaults, "enabled": want_on, "mode": 0}

                def view(o):
                    return ([(p["title"], sorted((x["title"], tuple(sorted(map(str, x.get("role_ids", [])))),
                                                  tuple(sorted(map(str, x.get("channel_ids", []))))) for x in p.get("options", [])))
                             for p in o.get("prompts", [])], sorted(map(str, o.get("default_channel_ids", []))), bool(o.get("enabled")))
                if view(cur) == view(body):
                    out("  = onboarding (no changes)")
                    counts["skipped"] += 1
                elif cur.get("prompts") and not update:
                    note("the server already has onboarding questions; run with --update to replace them with the blueprint's")
                else:
                    out(f"  ~ onboarding: {len(prompts)} question(s), {len(defaults)} default channel(s)"
                        + (", switched on" if want_on else "") + would)
                    counts["changed"] += 1
                    if not dry:
                        try:
                            client.call("PUT", f"/guilds/{gid}/onboarding", body)
                        except DiscordError as e:
                            if want_on:
                                body["enabled"] = False
                                try:
                                    client.call("PUT", f"/guilds/{gid}/onboarding", body)
                                    note(f"Discord wouldn't switch onboarding on ({explain(e)}); questions saved, turn it on in Server Settings > Onboarding")
                                except DiscordError as e2:
                                    warn(f"could not save onboarding: {explain(e2)}")
                            else:
                                warn(f"could not save onboarding: {explain(e)}")

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
        for k in ("roles", "channels", "emojis", "stickers", "messages", "automod"):
            merged.setdefault(k, {}).update(result[k])
        merged["problems"] = problems
        log.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        out(f"Log saved to {log}")
    if not getattr(args, "no_health", False):
        try:
            if dry:
                model = model_from_blueprint(bp)
            else:
                model = model_from_live(fetch_server(client, gid), client, gid)
            out("\n" + health_text(score_health(model), short=True))
        except Exception as e:  # the health check must never break a build
            out(f"\n(health check skipped: {e})")
    return 1 if problems else 0


# --------------------------------------------------------------------------- health score

VIEW_BIT, SEND_BIT, CONNECT_BIT = perm("VIEW_CHANNEL"), perm("SEND_MESSAGES"), perm("CONNECT")
# Channel-name words the health check looks for, in the languages references/languages.md covers.
HEALTH_WORDS = {
    "rules": ("rules", "normas", "reglas", "regras", "règles", "regles", "regeln", "peraturan", "ルール",
              "القوانين", "قوانين", "नियम", "niyam"),
    "welcome": ("welcome", "start", "bienvenida", "bienvenid", "empieza", "boas-vindas", "bienvenue", "willkommen",
                "selamat-datang", "ようこそ", "الترحيب", "ترحيب", "स्वागत", "swagat"),
    "announcement": ("announcement", "anuncio", "avisos", "annonce", "ankündigung", "pengumuman", "お知らせ",
                     "الإعلانات", "إعلانات", "घोषणा", "news", "devlog", "new-episode", "updates", "changelog"),
    "log": ("log", "registro", "journal", "protokoll", "catatan", "ログ", "سجل"),
}
INFO_WORDS = HEALTH_WORDS["rules"] + HEALTH_WORDS["welcome"] + HEALTH_WORDS["announcement"] + ("info", "faq")


def has_word(name: str, key: str) -> bool:
    n = name.lower()
    return any(w in n for w in HEALTH_WORDS[key])


def access_from_overwrites(ows, gid: str, rname: dict) -> dict:
    """Read Discord permission overwrites back into blueprint access keys (private_to, read_only, ...)."""
    m = ow_map(ows)
    ev_a, ev_d = m.get(str(gid), (0, 0))

    def names(bit):
        return sorted(rname[i] for i, (a, d) in m.items() if i != str(gid) and i in rname and a & bit)
    acc = {}
    if ev_d & VIEW_BIT:
        acc["private_to"] = names(VIEW_BIT)
    if ev_a & perm("CREATE_PRIVATE_THREADS") and ev_d & SEND_BIT:
        acc["thread_only"] = True
        if names(perm("MANAGE_THREADS")):
            acc["thread_staff"] = names(perm("MANAGE_THREADS"))
    elif ev_d & (SEND_BIT | CONNECT_BIT):
        acc["read_only"] = True
        w = sorted(set(names(SEND_BIT)) | set(names(CONNECT_BIT)))
        if w:
            acc["writers"] = w
    if ev_d & perm("ATTACH_FILES"):
        acc["media_to"] = names(perm("ATTACH_FILES"))
    return acc


def snowflake_days(sid) -> float | None:
    try:
        ms = (int(sid) >> 22) + 1420070400000
    except (TypeError, ValueError):
        return None
    return (time.time() * 1000 - ms) / 86400000


def model_from_blueprint(bp: dict) -> dict:
    chans, cats = [], []
    for ch in bp.get("channels", []):
        chans.append({"name": ch["name"], "type": ch.get("type", "text"), "topic": ch.get("topic", ""),
                      "category": None, "access": merged_access(None, ch), "idle_days": None})
    for c in bp.get("categories", []):
        cats.append({"name": c["name"], "access": merged_access(None, c)})
        for ch in c.get("channels", []):
            chans.append({"name": ch["name"], "type": ch.get("type", "text"), "topic": ch.get("topic", ""),
                          "category": c["name"], "access": merged_access(c, ch), "idle_days": None})
    am = bp.get("automod")
    kinds = set()
    if am:
        kinds = {r["trigger_type"] for r in automod_rules(am, lambda n: "x", {}, lambda m: None)}
    self_roles = bool(bp.get("onboarding")) or any(ch.get("reactions") for c in bp.get("categories", []) for ch in c.get("channels", []))
    return {"source": "blueprint", "members": None, "everyone_perms": None, "bot_below": None,
            "roles": [{"name": r["name"], "perms": role_permissions(r), "managed": False} for r in bp.get("roles", [])],
            "channels": chans, "categories": cats, "automod": kinds,
            "automod_presets": (AM_LEVELS[am.get("level", "standard")]["presets"] if am else []),
            "emojis": len(bp.get("emojis", [])), "stickers": len(bp.get("stickers", [])), "emoji_cap": 50,
            "self_roles": self_roles, "language": bp.get("language")}


def model_from_live(s: dict, client, gid: str) -> dict:
    roles = s["roles"]
    rname = {r["id"]: r["name"] for r in roles if not r.get("managed") and r["id"] != gid}
    by_id = {c["id"]: c for c in s["channels"]}
    chans, cats = [], []
    for c in s["channels"]:
        tname = TYPE_NAMES.get(c["type"], "text")
        acc = access_from_overwrites(c.get("permission_overwrites", []), gid, rname)
        if tname == "category":
            cats.append({"name": c["name"], "access": acc, "id": c["id"]})
            continue
        idle = None
        if family(tname) == "text" and tname != "forum":
            idle = snowflake_days(c.get("last_message_id")) if c.get("last_message_id") else snowflake_days(c["id"])
        parent = by_id.get(c.get("parent_id"))
        chans.append({"name": c["name"], "type": tname, "topic": c.get("topic") or "",
                      "category": parent["name"] if parent else None, "access": acc, "idle_days": idle})
    try:
        g = client.call("GET", f"/guilds/{gid}?with_counts=true") or {}
    except DiscordError:
        g = {}
    everyone = next((r for r in roles if r["id"] == gid), {})
    tier = s["guild"].get("premium_tier", 0)
    bot_top = s.get("bot_top") or (0, 0)
    above = [r["name"] for r in roles if not r.get("managed") and r["id"] != gid and rank(r) >= bot_top
             and not int(r.get("permissions", 0)) & ADMIN_BIT]
    rule_names = [r["name"] for r in s.get("automod", [])]
    preset = next((r for r in s.get("automod", []) if r["trigger_type"] == AM_PRESET), None)
    has_onboarding = any("roles" in c["name"] for c in s["channels"])
    return {"source": "live", "members": g.get("approximate_member_count"),
            "everyone_perms": int(everyone.get("permissions", 0)), "bot_below": above,
            "roles": [{"name": r["name"], "perms": int(r.get("permissions", 0)), "managed": bool(r.get("managed"))}
                      for r in roles if r["id"] != gid],
            "channels": chans, "categories": cats, "automod": {r["trigger_type"] for r in s.get("automod", [])},
            "automod_presets": (preset or {}).get("trigger_metadata", {}).get("presets", []),
            "automod_names": rule_names,
            "emojis": len(s["emojis"]), "stickers": len(s["stickers"]), "emoji_cap": EMOJI_SLOTS.get(tier, 50),
            "self_roles": has_onboarding, "language": None,
            "server_age_days": snowflake_days(gid)}


def score_health(m: dict) -> dict:
    """Score a server (live or planned) 0-100 with sections, findings and concrete fixes."""
    sections = {k: {"max": v, "lost": 0, "items": []} for k, v in
                (("Structure", 25), ("Safety", 35), ("Privacy", 15), ("Engagement", 15), ("Clarity", 10))}

    def ok(sec, text):
        sections[sec]["items"].append(("ok", text, ""))

    def bad(sec, pts, text, fix):
        s = sections[sec]
        pts = min(pts, s["max"] - s["lost"])
        s["lost"] += pts
        s["items"].append(("bad" if pts else "info", text, fix))

    texts = [c for c in m["channels"] if family(c["type"]) == "text"]
    voices = [c for c in m["channels"] if family(c["type"]) == "voice"]
    members = m.get("members")
    size = "new" if members is None else f"~{members} members"
    ideal = 18 if not members or members < 100 else 28 if members < 1000 else 45
    if len(texts) > ideal:
        bad("Structure", min(10, len(texts) - ideal), f"{len(texts)} text channels for a {size} server feels empty (aim for {ideal} or fewer)",
            "merge quiet channels: remove them from the blueprint's categories and list them in \"remove\", then apply --update --confirm-delete")
    else:
        ok("Structure", f"{len(texts)} text channels - a good size for a {size} server")
    if (members is None or members < 100) and len(voices) > 5:
        bad("Structure", 3, f"{len(voices)} voice channels; small servers rarely fill more than 2-3",
            "keep 2-3 general voice channels; remove the rest via \"remove\" + apply --update --confirm-delete")
    for word, pts, label in (("rules", 5, "rules"), ("welcome", 4, "welcome"), ("announcement", 3, "announcements")):
        if any(has_word(c["name"], word) for c in texts):
            ok("Structure", f"has {'an' if label[0] in 'aeiou' else 'a'} {label} channel")
        else:
            bad("Structure", pts, f"no {label} channel", f"add a '{label}' channel to START HERE in the blueprint and run apply")

    # ---- safety
    am = m["automod"]
    if not am:
        bad("Safety", 14, "no AutoMod rules - scams and slurs aren't filtered",
            "add an \"automod\" block (references/community-systems.md, section 1) and run apply")
    else:
        for t, pts, label in ((AM_PRESET, 4, "slur/adult-content filter"), (AM_KEYWORD, 4, "scam/keyword filter"),
                              (AM_MENTION, 3, "mention-spam protection"), (AM_SPAM, 2, "spam filter")):
            if t in am:
                ok("Safety", f"AutoMod {label} on")
            else:
                bad("Safety", pts, f"no AutoMod {label}", "add or complete the \"automod\" block and run apply --update")
        if am and AM_PRESET_SLURS not in (m.get("automod_presets") or [AM_PRESET_SLURS]):
            bad("Safety", 2, "the preset filter doesn't block slurs", "use at least the 'relaxed' AutoMod level")
    ev = m.get("everyone_perms")
    if ev is not None:
        if ev & perm("MENTION_EVERYONE"):
            bad("Safety", 6, "@everyone can ping @everyone/@here (a favourite of raiders)",
                "Server Settings > Roles > @everyone > turn off 'Mention @everyone, @here and All Roles'")
        else:
            ok("Safety", "members can't mass-ping")
        if ev & ADMIN_BIT:
            bad("Safety", 15, "@everyone has Administrator!", "Server Settings > Roles > @everyone > turn off Administrator now")
    info_open = [c["name"] for c in texts if any(w in c["name"].lower() for w in INFO_WORDS)
                 and not (c["access"].get("read_only") or c["access"].get("private_to") or c["access"].get("thread_only"))]
    if info_open:
        bad("Safety", min(6, 2 * len(info_open)), f"anyone can post in info channels: {', '.join(info_open[:4])}",
            "set \"read_only\": true with \"writers\" on START HERE and run apply --update")
    elif texts:
        ok("Safety", "info channels are read-only")
    admins = [r["name"] for r in m["roles"] if r["perms"] & ADMIN_BIT and not r["managed"]]
    if len(admins) > 1:
        bad("Safety", 4, f"{len(admins)} human roles have Administrator: {', '.join(admins[:4])}",
            "keep Administrator on one owner role; give staff the 'admin'/'moderator' presets instead (apply --update)")
    bot_admins = [r["name"] for r in m["roles"] if r["perms"] & ADMIN_BIT and r["managed"]]
    if bot_admins and m["source"] == "live":
        bad("Safety", 2, f"bots with Administrator: {', '.join(bot_admins[:4])}",
            "after setup, remove Administrator from bot roles in Server Settings > Roles")
    if m.get("bot_below"):
        bad("Safety", 3, f"the builder bot sits below roles it may need to manage: {', '.join(m['bot_below'][:4])}",
            "Server Settings > Roles: drag the bot's role above them (or ignore if you won't edit them)")
    staff_log = [c for c in texts if has_word(c["name"], "log")]
    if not staff_log:
        bad("Safety", 4, "no mod-log channel for AutoMod alerts and staff notes",
            "add a 'mod-log' channel to a private STAFF category and set automod.alert_channel to it")
    elif not any(c["access"].get("private_to") for c in staff_log):
        bad("Safety", 4, "the mod-log channel is visible to everyone", "put it in a category with \"private_to\": [staff roles]")
    else:
        ok("Safety", "private mod-log exists")

    # ---- privacy
    private_cats = {c["name"]: c for c in m["categories"] if c["access"].get("private_to")}
    leaks = [c["name"] for c in m["channels"] if c["category"] in private_cats and not c["access"].get("private_to")]
    if leaks:
        bad("Privacy", min(15, 5 * len(leaks)), f"channels inside private categories are visible to everyone: {', '.join(leaks[:4])}",
            "run apply --update with the category's private_to (channels inherit it), or sync permissions in channel settings")
    elif private_cats:
        ok("Privacy", f"{len(private_cats)} private categor{'y' if len(private_cats) == 1 else 'ies'}, no leaks")
    else:
        ok("Privacy", "no private areas to check")

    # ---- engagement
    cap = m.get("emoji_cap", 50)
    if m["emojis"] < 5:
        bad("Engagement", 4, f"only {m['emojis']} custom emoji(s) of {cap} free slots",
            "design 6-10 branded emojis (SKILL.md step 6) and add them to the blueprint's \"emojis\"")
    else:
        ok("Engagement", f"{m['emojis']} custom emojis")
    if m["stickers"] == 0:
        bad("Engagement", 1, "no stickers", "add 1-5 stickers (catchphrases, mascot) to \"stickers\"")
    if not m["self_roles"]:
        bad("Engagement", 3, "no way to pick ping/interest roles", "add onboarding questions or a #get-roles post with reactions")
    else:
        ok("Engagement", "members can pick their own roles")
    if m["source"] == "live" and (m.get("server_age_days") or 0) > 14:
        idle = [c["name"] for c in texts if c["idle_days"] is not None and c["idle_days"] > 30]
        if idle:
            bad("Engagement", min(6, len(idle)), f"{len(idle)} channel(s) quiet for 30+ days: {', '.join(idle[:5])}",
                "merge or remove them (\"remove\" + apply --update --confirm-delete), or give them a weekly ritual")
        else:
            ok("Engagement", "every text channel was used in the last 30 days")

    # ---- clarity
    no_topic = [c["name"] for c in texts if not c["topic"] and c["type"] != "forum"]
    if texts and len(no_topic) / len(texts) > 0.3:
        bad("Clarity", min(6, len(no_topic) // 2 + 1), f"{len(no_topic)} of {len(texts)} text channels have no topic",
            "add a one-line \"topic\" to each channel and run apply --update")
    else:
        ok("Clarity", "channels explain what they're for")
    if len(m["categories"]) == 0 and len(m["channels"]) > 6:
        bad("Clarity", 4, "no categories", "group channels into 3-6 categories in the blueprint")

    total = 100 - sum(s["lost"] for s in sections.values())
    return {"score": max(0, total), "sections": sections, "source": m["source"]}


def health_text(h: dict, short: bool = False) -> str:
    grade = "excellent" if h["score"] >= 90 else "good" if h["score"] >= 75 else "needs work" if h["score"] >= 55 else "at risk"
    lines = [f"Server health: {h['score']}/100 ({grade}){' - planned layout' if h['source'] == 'blueprint' else ''}"]
    fixes = []
    for name, s in h["sections"].items():
        lines.append(f"  {name}: {s['max'] - s['lost']}/{s['max']}")
        for kind, text, fix in s["items"]:
            if kind == "ok":
                if not short:
                    lines.append(f"    ✓ {text}")
            else:
                lines.append(f"    ✗ {text}")
                fixes.append(f"  - {text}: {fix}")
    if fixes:
        lines.append("Fixes:")
        lines += fixes
    return "\n".join(lines)


def cmd_health(args, client: Client | None = None) -> int:
    if args.blueprint:
        bp, errors, _ = load_blueprint(args.blueprint)
        for e in errors:
            out(f"ERROR: {e}")
        h = score_health(model_from_blueprint(bp))
    else:
        if not args.guild:
            sys.exit("Give a BLUEPRINT file, or --guild ID to check a live server.")
        client = client or Client(load_token(args.env_file))
        try:
            s = fetch_server(client, args.guild)
        except DiscordError as e:
            out(explain(e))
            return 1
        out(f"Server: {s['guild']['name']}")
        h = score_health(model_from_live(s, client, args.guild))
    out(health_text(h))
    return 0


# --------------------------------------------------------------------------- export (live server -> shareable blueprint)

ID_RE = re.compile(r"\b\d{17,20}\b")
INVITE_RE = re.compile(r"(?i)(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+")


def perms_to_spec(value: int):
    for name in ("member", "moderator", "admin"):
        if perm(*PRESETS[name]) == value:
            return name
    if value == 0:
        return "none"
    return [n for n, b in sorted(BITS.items(), key=lambda kv: kv[1]) if value & (1 << b)]


def cmd_export(args, client: Client | None = None) -> int:
    client = client or Client(load_token(args.env_file))
    gid = args.guild
    try:
        s = fetch_server(client, gid)
    except DiscordError as e:
        out(explain(e))
        return 1
    guild, roles, chans = s["guild"], s["roles"], s["channels"]
    bot_id = s["me"]["id"]
    community = "COMMUNITY" in guild.get("features", [])
    rname = {r["id"]: r["name"] for r in roles if not r.get("managed") and r["id"] != gid}
    cname = {c["id"]: c["name"] for c in chans}
    ename = {e["id"]: e["name"] for e in s["emojis"]}

    def clean(text: str) -> str:
        text = re.sub(r"<#(\d+)>", lambda m: "{#" + cname[m.group(1)] + "}" if m.group(1) in cname else "#channel", text or "")
        text = re.sub(r"<@&(\d+)>", lambda m: "{@" + rname[m.group(1)] + "}" if m.group(1) in rname else "@role", text)
        text = re.sub(r"<@!?\d+>", "@member", text)
        text = re.sub(r"<a?:(\w{2,32}):\d+>", lambda m: "{:" + m.group(1) + ":}", text)
        text = INVITE_RE.sub("(invite link removed)", text)
        return ID_RE.sub("", text)

    bp: dict = {"server_name": guild["name"], "_exported_from": "discord-server-builder export",
                "roles": [], "categories": []}
    for r in sorted((r for r in roles if r["id"] in rname), key=rank, reverse=True):
        item = {"name": r["name"], "permissions": perms_to_spec(int(r.get("permissions", 0)))}
        if r.get("color"):
            item["color"] = f"#{r['color']:06X}"
        for k in ("hoist", "mentionable"):
            if r.get(k):
                item[k] = True
        if int(r.get("permissions", 0)) & ADMIN_BIT:
            item["permissions"] = "admin"
            item["_note"] = "had Administrator; exported as the 'admin' preset (shared blueprints never grant Administrator)"
        bp["roles"].append(item)

    def channel_item(c, parent_acc):
        tname = TYPE_NAMES.get(c["type"], "text")
        it = {"name": c["name"]}
        if tname != "text":
            it["type"] = tname
        if c.get("topic"):
            it["topic"] = clean(c["topic"])
        if c.get("rate_limit_per_user"):
            it["slowmode"] = c["rate_limit_per_user"]
        if tname == "voice" and c.get("user_limit"):
            it["user_limit"] = c["user_limit"]
        acc = access_from_overwrites(c.get("permission_overwrites", []), gid, rname)
        for k in ACCESS_KEYS:
            if k in acc and acc[k] != (parent_acc or {}).get(k):
                it[k] = acc[k]
            elif k not in acc and (parent_acc or {}).get(k):
                it[k] = [] if isinstance(parent_acc[k], list) else False
        if family(tname) == "text" and tname != "forum":
            try:
                msgs = client.call("GET", f"/channels/{c['id']}/messages?limit=50") or []
            except DiscordError:
                msgs = []
            mine = sorted([m for m in msgs if m.get("author", {}).get("id") == bot_id and m.get("type", 0) == 0],
                          key=lambda m: int(m["id"]))
            if mine:
                it["message"] = "\n".join(clean(m["content"]) for m in mine)
                if mine[0].get("pinned"):
                    it["pin"] = True
                reacts = []
                for rr in mine[0].get("reactions", []):
                    e = rr.get("emoji") or {}
                    if rr.get("me"):
                        reacts.append("{:" + e["name"] + ":}" if e.get("id") else e.get("name"))
                if reacts:
                    it["reactions"] = reacts
        return it

    def order(cs):
        return sorted(cs, key=lambda c: (family(TYPE_NAMES.get(c["type"], "text")) == "voice", c["position"], int(c["id"])))
    top = [c for c in chans if not c.get("parent_id") and c["type"] != 4]
    if top:
        bp["channels"] = [channel_item(c, None) for c in order(top)]
    for cat in sorted((c for c in chans if c["type"] == 4), key=lambda c: (c["position"], int(c["id"]))):
        acc = access_from_overwrites(cat.get("permission_overwrites", []), gid, rname)
        item = {"name": cat["name"], **acc,
                "channels": [channel_item(c, acc) for c in order([x for x in chans if x.get("parent_id") == cat["id"]])]}
        bp["categories"].append(item)

    sb = {r["name"]: r for r in s.get("automod", []) if r["name"].startswith(AM_PREFIX)}
    if sb:
        pre = sb.get(AM_PREFIX + "Slurs & adult content", {}).get("trigger_metadata", {}).get("presets", [])
        level = next((k for k, v in AM_LEVELS.items() if sorted(v["presets"]) == sorted(pre)), "standard")
        any_rule = next(iter(sb.values()))
        alert = next((a["metadata"].get("channel_id") for a in any_rule.get("actions", []) if a["type"] == 2), None)
        am = {"level": level}
        if alert in cname:
            am["alert_channel"] = cname[alert]
        am["exempt_roles"] = [rname[i] for i in any_rule.get("exempt_roles", []) if i in rname]
        am["exempt_channels"] = [cname[i] for i in any_rule.get("exempt_channels", []) if i in cname]
        bw = sb.get(AM_PREFIX + "Blocked words", {}).get("trigger_metadata", {}).get("keyword_filter", [])
        if bw:
            am["blocked_words"] = bw
        aw = sb.get(AM_PREFIX + "Slurs & adult content", {}).get("trigger_metadata", {}).get("allow_list", [])
        if aw:
            am["allowed_words"] = aw
        sw = [w for w in sb.get(AM_PREFIX + "Scams, invites & spam links", {}).get("trigger_metadata", {}).get("keyword_filter", [])
              if w not in AM_SCAM_WORDS]
        if sw:
            am["scam_words"] = sw
        bp["automod"] = am
    if guild.get("system_channel_id") in cname:
        flags = int(guild.get("system_channel_flags") or 0)
        bp["welcome"] = {"system_channel": cname[guild["system_channel_id"]],
                         "join_messages": not flags & SYS_SUPPRESS_JOIN, "boost_messages": not flags & SYS_SUPPRESS_BOOST,
                         "setup_tips": not flags & SYS_SUPPRESS_TIPS, "join_sticker_replies": not flags & SYS_SUPPRESS_JOIN_REPLIES}
    if community:
        try:
            ws = client.call("GET", f"/guilds/{gid}/welcome-screen") or {}
            if ws.get("welcome_channels"):
                bp.setdefault("welcome", {})["screen"] = {
                    "description": clean(ws.get("description") or ""),
                    "channels": [{"channel": cname[w["channel_id"]], "description": clean(w.get("description", "")),
                                  **({"emoji": ("{:" + w["emoji_name"] + ":}") if w.get("emoji_id") else w["emoji_name"]}
                                     if w.get("emoji_name") else {})}
                                 for w in ws["welcome_channels"] if w.get("channel_id") in cname]}
        except DiscordError:
            pass
        try:
            ob = client.call("GET", f"/guilds/{gid}/onboarding") or {}
            if ob.get("prompts"):
                bp["onboarding"] = {
                    "default_channels": [cname[i] for i in ob.get("default_channel_ids", []) if i in cname],
                    "enable": bool(ob.get("enabled")),
                    "questions": [{"title": p["title"], "single_select": bool(p.get("single_select")),
                                   "required": bool(p.get("required")), "dropdown": p.get("type") == 1,
                                   "options": [{"title": o["title"], "description": o.get("description") or "",
                                                "roles": [rname[i] for i in o.get("role_ids", []) if i in rname],
                                                "channels": [cname[i] for i in o.get("channel_ids", []) if i in cname],
                                                **({"emoji": (o.get("emoji") or {}).get("name")} if (o.get("emoji") or {}).get("name")
                                                   and not (o.get("emoji") or {}).get("id") else {})}
                                               for o in p.get("options", [])]}
                                  for p in ob["prompts"]]}
        except DiscordError:
            pass
    if s["emojis"]:
        bp["_notes"] = [f"The server had {len(s['emojis'])} custom emojis ({', '.join(e['name'] for e in s['emojis'][:10])}"
                        f"{'...' if len(s['emojis']) > 10 else ''}). Images aren't exported: add your own files and an "
                        "\"emojis\" list to include emojis."]
    text = json.dumps(bp, indent=2, ensure_ascii=False)
    leftover = ID_RE.findall(text)
    if leftover:  # belt and braces: nothing ID-shaped may leave the server
        text = ID_RE.sub("", text)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    nchan = sum(len(c["channels"]) for c in bp["categories"]) + len(bp.get("channels", []))
    out(f"Exported {guild['name']}: {len(bp['roles'])} roles, {len(bp['categories'])} categories, {nchan} channels"
        + (", AutoMod" if "automod" in bp else "") + (", onboarding" if "onboarding" in bp else "") + f" -> {args.out}")
    out("Removed: all IDs, members, message authors and invite links. Review the starter texts before sharing.")
    return 0


# --------------------------------------------------------------------------- preview (HTML mockup)

RTL_LANGS = ("ar", "he", "fa", "ur", "ps", "yi", "dv", "ckb")


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def render_preview(bp: dict, base: Path) -> str:
    lang = str(bp.get("language") or "en")
    rtl = lang.split("-")[0].lower() in RTL_LANGS
    roles = bp.get("roles", [])
    rcolor = {r["name"].lower(): (r.get("color") or "#B5BAC1") for r in roles}
    icons = {"text": "#", "announcement": "📢", "forum": "💬", "voice": "🔊", "stage": "🎙️"}

    def fmt(text: str) -> str:
        t = _esc(text.replace("{server}", bp.get("server_name") or "Server"))
        t = re.sub(r"\{#([^{}]+)\}", lambda m: f'<span class="mention">#{m.group(1)}</span>', t)
        t = re.sub(r"\{@([^{}]+)\}", lambda m: f'<span class="mention" style="color:{_esc(rcolor.get(m.group(1).lower(), "#C9CDFB"))}">@{m.group(1)}</span>', t)
        t = re.sub(r"\{:(\w{2,32}):\}", lambda m: f'<span class="emo">:{m.group(1)}:</span>', t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\|\|(.+?)\|\|", r'<span class="spoiler">\1</span>', t)
        return t.replace("\n", "<br>")

    def chan(ch, parent):
        t = ch.get("type", "text")
        acc = merged_access(parent, ch)
        lock = ' <span class="lock" title="private">🔒</span>' if acc.get("private_to") else ""
        ro = ' <span class="tag">read-only</span>' if acc.get("read_only") else ""
        tk = ' <span class="tag">tickets</span>' if acc.get("thread_only") else ""
        return (f'<div class="ch"><span class="ic">{icons.get(t, "#")}</span><span class="nm">{_esc(ch["name"])}</span>'
                f'{lock}{ro}{tk}</div>')

    side = []
    for ch in bp.get("channels", []):
        side.append(chan(ch, None))
    for c in bp.get("categories", []):
        lock = " 🔒" if c.get("private_to") else ""
        side.append(f'<div class="cat">⌄ {_esc(c["name"])}{lock}</div>')
        side += [chan(ch, c) for ch in c.get("channels", [])]

    first = None
    for c in bp.get("categories", []):
        for ch in c.get("channels", []):
            if ch.get("message") and not first:
                first = (ch, c)
    msg_html = ""
    if first:
        ch, _ = first
        msg_html = (f'<div class="head"><span class="ic">#</span>{_esc(ch["name"])}'
                    f'<span class="topic">{_esc(ch.get("topic", ""))}</span></div>'
                    f'<div class="msg"><div class="av">🤖</div><div><div class="who">Server Builder <span class="bot">BOT</span>'
                    f'{" <span class=tag>📌 pinned</span>" if ch.get("pin") else ""}</div><div class="txt">{fmt(ch["message"])}</div>'
                    + ("".join(f'<span class="react">{fmt(x) if x.startswith("{") else _esc(x)} 1</span>' for x in ch.get("reactions", [])))
                    + "</div></div>")

    groups = []
    for r in roles:
        color = _esc(r.get("color") or "#B5BAC1")
        groups.append(f'<div class="role"><span class="dot" style="background:{color}"></span>'
                      f'<span style="color:{color}">{_esc(r["name"])}</span>{" ▲" if r.get("hoist") else ""}</div>')
    emo = []
    for e in bp.get("emojis", []):
        img = ""
        p = base / e.get("file", "")
        if e.get("file") and p.is_file() and p.stat().st_size <= 300_000:
            fmt_ = sniff(p.read_bytes())
            if fmt_ in MIME and fmt_ != "lottie":
                img = f'<img src="data:{MIME[fmt_]};base64,{base64.b64encode(p.read_bytes()).decode()}" alt="">'
        emo.append(f'<span class="emoji">{img}<small>:{_esc(e["name"])}:</small></span>')
    extras = []
    if bp.get("automod"):
        extras.append(f"🛡️ AutoMod: {_esc(bp['automod'].get('level', 'standard'))}")
    if bp.get("onboarding"):
        extras.append(f"🧭 Onboarding: {len(bp['onboarding'].get('questions', []))} question(s)")
    if (bp.get("welcome") or {}).get("screen"):
        extras.append("👋 Welcome screen")

    css = """
:root{--bg:#313338;--side:#2B2D31;--rail:#1E1F22;--text:#DBDEE1;--mute:#949BA4;--hover:#35373C;--accent:#5865F2}
@media (prefers-color-scheme: light){:root:not([data-theme=dark]){--bg:#FFFFFF;--side:#F2F3F5;--rail:#E3E5E8;--text:#313338;--mute:#5C5E66;--hover:#E0E1E5}}
:root[data-theme=dark]{--bg:#313338;--side:#2B2D31;--rail:#1E1F22;--text:#DBDEE1;--mute:#949BA4;--hover:#35373C}
*{box-sizing:border-box}body{margin:0;background:var(--rail);color:var(--text);font:15px/1.4 "gg sans","Noto Sans","Segoe UI",system-ui,sans-serif}
.app{display:grid;grid-template-columns:72px 260px 1fr 240px;height:100vh}
.rail{background:var(--rail);padding:12px 0;display:flex;flex-direction:column;align-items:center;gap:8px}
.srv{width:48px;height:48px;border-radius:16px;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:700}
.side{background:var(--side);overflow:auto}.title{padding:14px 16px;font-weight:700;border-bottom:1px solid rgba(0,0,0,.25);box-shadow:0 1px 0 rgba(0,0,0,.1)}
.cat{margin:16px 8px 4px 12px;font-size:12px;font-weight:700;letter-spacing:.02em;color:var(--mute);text-transform:uppercase}
.ch{margin:1px 8px;padding:6px 8px;border-radius:4px;color:var(--mute);display:flex;gap:6px;align-items:center}.ch:hover{background:var(--hover);color:var(--text)}
.ic{opacity:.8;width:18px;text-align:center}.nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lock{font-size:11px}
.tag{font-size:10px;background:var(--hover);border-radius:3px;padding:0 4px;color:var(--mute)}
.main{background:var(--bg);overflow:auto}.head{padding:12px 16px;font-weight:700;border-bottom:1px solid rgba(0,0,0,.2);display:flex;gap:8px;align-items:center}
.topic{font-weight:400;color:var(--mute);font-size:13px;margin-inline-start:12px}
.msg{display:flex;gap:14px;padding:18px}.av{width:40px;height:40px;border-radius:50%;background:var(--accent);display:grid;place-items:center;flex:none}
.who{font-weight:600}.bot{background:var(--accent);color:#fff;font-size:10px;border-radius:3px;padding:1px 4px;margin-inline-start:4px}
.txt{margin-top:4px}.mention{background:rgba(88,101,242,.3);border-radius:3px;padding:0 2px;color:#C9CDFB}
code{background:var(--side);padding:1px 4px;border-radius:3px}.spoiler{background:#1E1F22;color:#1E1F22;border-radius:3px}
.react{display:inline-block;margin:8px 6px 0 0;padding:2px 8px;border-radius:8px;background:var(--side);border:1px solid var(--accent);font-size:13px}
.members{background:var(--side);padding:16px;overflow:auto}.members h4{margin:0 0 8px;font-size:12px;color:var(--mute);text-transform:uppercase}
.role{display:flex;gap:8px;align-items:center;padding:4px 0}.dot{width:10px;height:10px;border-radius:50%;flex:none}
.emojis{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.emoji{display:flex;flex-direction:column;align-items:center;font-size:11px;color:var(--mute)}
.emoji img{width:32px;height:32px;object-fit:contain}.extras{padding:0 18px 18px;color:var(--mute);font-size:13px}.extras span{margin-inline-end:14px}
@media (max-width:900px){.app{grid-template-columns:1fr;height:auto}.rail,.members{display:none}.side{max-height:none}}
"""
    return f"""<!doctype html>
<html lang="{_esc(lang)}" dir="{'rtl' if rtl else 'ltr'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(bp.get('server_name') or 'Server')} preview</title><style>{css}</style></head>
<body><div class="app">
<nav class="rail"><div class="srv">{_esc((bp.get('server_name') or 'S')[:2])}</div></nav>
<aside class="side"><div class="title">{_esc(bp.get('server_name') or 'Server')}</div>{''.join(side)}</aside>
<main class="main">{msg_html}<div class="extras">{''.join(f'<span>{x}</span>' for x in extras)}</div></main>
<aside class="members"><h4>Roles — {len(roles)}</h4>{''.join(groups)}
{'<h4 style="margin-top:16px">Emojis</h4><div class="emojis">' + ''.join(emo) + '</div>' if emo else ''}</aside>
</div></body></html>
"""


def cmd_preview(args) -> int:
    bp, errors, warnings = load_blueprint(args.blueprint)
    print_plan(bp)
    for e in errors:
        out(f"ERROR: {e}")
    html = render_preview(bp, Path(args.blueprint).resolve().parent)
    dest = Path(args.out or Path(args.blueprint).with_suffix(".preview.html"))
    dest.write_text(html, encoding="utf-8")
    out(f"\nPreview written to {dest} (open it in a browser; it makes no network requests).")
    return 1 if errors else 0


def cmd_delete(args, client: Client | None = None) -> int:
    names = {"channels": args.channel or [], "roles": args.role or [],
             "emojis": args.emoji or [], "stickers": args.sticker or [],
             "automod": getattr(args, "automod", None) or []}
    if not any(names.values()):
        sys.exit("Name at least one --channel, --role, --emoji, --sticker or --automod to delete.")
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
        try:
            live_automod = {r["id"]: r for r in (client.call("GET", f"/guilds/{gid}/auto-moderation/rules") or [])}
        except DiscordError:
            live_automod = {}
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
                            ("sticker", "stickers", live_stickers), ("automod", "automod", live_automod)):
        for name, xid in log.get(key, {}).items():
            if xid in live:
                targets.append((kind, xid, ("@" if kind == "role" else ("AutoMod rule " if kind == "automod" else f"{kind} ")) + name))
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
    a.add_argument("--no-health", action="store_true", help="skip the health score at the end")
    h = sub.add_parser("health", help="score a live server (--guild) or a blueprint 0-100 with fixes")
    h.add_argument("blueprint", nargs="?")
    h.add_argument("--guild")
    x = sub.add_parser("export", help="turn a live server into a clean, shareable blueprint")
    x.add_argument("--guild", required=True)
    x.add_argument("out")
    p = sub.add_parser("preview", help="write a Discord-style HTML mockup of a blueprint")
    p.add_argument("blueprint")
    p.add_argument("--out")
    d = sub.add_parser("delete", help="delete named channels/roles/emojis/stickers")
    d.add_argument("--guild", required=True)
    d.add_argument("--channel", action="append")
    d.add_argument("--role", action="append")
    d.add_argument("--emoji", action="append")
    d.add_argument("--sticker", action="append")
    d.add_argument("--automod", action="append", help="AutoMod rule name")
    d.add_argument("--confirm-delete", action="store_true")
    u = sub.add_parser("undo", help="delete what earlier applies created, from the .result.json log")
    u.add_argument("result")
    u.add_argument("--guild")
    u.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return {"validate": cmd_validate, "check": cmd_check, "inspect": cmd_inspect, "apply": cmd_apply,
            "delete": cmd_delete, "undo": cmd_undo, "health": cmd_health, "export": cmd_export,
            "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
