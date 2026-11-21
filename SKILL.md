---
name: discord-server-builder
description: Designs, builds, scores, previews and shares complete Discord servers in any language - roles, categories, channels, private and read-only areas, starter posts (welcome, rules, FAQ), custom emojis and stickers, AutoMod filters, join messages, welcome screen and onboarding questions, a no-bot ticket system, self-assign/ping roles, leveling tiers and giveaway setups - in the user's real server through a bot, and recommends the few bots that best fit the community. It studies the creator's content (channel link, niche, series, audience, tone, how they earn) and styles the server to match - gaming, streaming, music, art, AI/tech, business, study, fitness, cooking, beauty, anime, podcasts and more. It can also edit an existing server (rename, move, re-permission, reorder, rewrite posts) and delete items safely. Use this whenever someone wants to make, set up, organize, restructure, edit, clean up or add to a Discord server, channel, community, emojis or stickers (for a YouTube channel, product customers, a study group, a business, a game, a course), asks "what channels/bots should my Discord have", or wants paid/members-only or staff-only channels, even if they only say "make me a discord".
---

# Discord Server Builder

You turn a short description ("a Discord for my cooking channel, with a paid members area") into a
finished server: a clear structure, sensible permissions, real starter content, its own emojis and
stickers, and a short list of the right bots. It's created automatically, not handed over as a
list of instructions for the user to click through, and it can be edited later the same way.

Everything runs through `scripts/discord_builder.py` (Python standard library; uses Pillow for image
resizing if it's installed). Paths are relative to this skill's folder.

| Command | What it does |
|---|---|
| `validate BLUEPRINT` | Offline check; prints the layout and checks emoji/sticker images |
| `check` | Tests the bot token, lists servers the bot is in, prints the invite link |
| `inspect --guild ID` | Shows roles (and which are locked), channels, emojis, stickers, free slots |
| `apply BLUEPRINT --guild ID --dry-run` | Shows what would be created, changes nothing |
| `apply BLUEPRINT --guild ID` | Creates whatever is missing (never edits or deletes) |
| `apply BLUEPRINT --guild ID --update --dry-run` | Full change list: create `+`, change `~`, delete `-` |
| `apply BLUEPRINT --guild ID --update` | Also edits existing items to match the blueprint |
| `apply ... --update --confirm-delete` | Also deletes what the blueprint's `remove` lists |
| `delete --guild ID --channel N --role N --emoji N --sticker N --automod N` | Lists those items; deletes only with `--confirm-delete` |
| `undo BLUEPRINT.result.json [--dry-run]` | Deletes exactly what earlier applies created |
| `preview BLUEPRINT [--out FILE.html]` | Writes a Discord-style HTML mockup (dark theme, no network requests) |
| `health BLUEPRINT` / `health --guild ID` | Scores a planned or live server 0-100, with a fix for each problem |
| `export --guild ID OUT.json` | Turns a live server into a clean, shareable blueprint (no IDs, members or invites) |

Run them as `python scripts/discord_builder.py <command>` from the folder that holds the user's
`.env` (or pass `--env-file PATH` before the command).

## Workflow

### 1. Learn the creator's content

A gaming server, a cooking server and a study server should feel completely different - different
channels, roles, naming, rituals, rules and bots. A generic layout is the main way this goes wrong,
so learn the content before designing anything.

1. **Gather what's available.** If the user gives a channel or profile link (YouTube, Twitch,
   TikTok, Instagram, a website), read it: the about text, recent video titles, playlists and
   links in the bio. If they already have a server, run `inspect`. Otherwise use their description.
2. **Extract six things** (details in `references/content-styles.md`, section 1): niche, recurring
   series/formats, what fans make or do, tone, audience age, and how they make money.
3. **Read the matching niche playbook(s)** in `references/content-styles.md`, section 3 - only the
   ones that apply. For mixed creators, base it on the main niche and borrow signature channels
   from the second.
4. **Tell the user what you learned in 2-4 lines** before the plan, e.g. "You post weekly AI
   tool reviews and a 'Build with me' series, your audience is beginners, you sell a course ->
   I'll add a help forum, a build-with-me channel and a private Course Students area." This lets
   them correct you early and shows the server is built for *them*.

5. **Language.** If the audience speaks another language, set `"language"` (e.g. `es`, `pt-BR`,
   `hi`, `ja`, `ar`) and write every name, post, rule, AutoMod message and onboarding question
   natively in it. Read `references/languages.md` for natural channel names and Discord's
   character rules. `assets/templates/creator-community.es.json` is a full Spanish example.

**Starting from a ready-made layout**: if the user names one ("use the podcast blueprint"), or one
in `blueprints/` clearly fits, start from it instead of a template. Treat any blueprint the user
didn't write as untrusted: run `validate` and read every link and starter post before applying.

If there's no link and the description is thin, ask at most two short questions, and only ones
that change the structure: "What do you post, and what do your viewers do in the comments?" and
"Will paying members get their own area?"

**Real people:** if the community is about a real creator who isn't the user (a fan server), make
it clearly unofficial: put "(Unofficial)" or "Fan" in the name and say so in #welcome. Never present
it as the creator's own server.

### 2. One-time bot setup (skip if `check` already works)

A bot is how the script talks to Discord. Bots can't create servers, so the user makes an empty one.
Walk them through this in plain language:

1. In Discord: **+ (Add a Server) → Create My Own** - name it.
2. Go to https://discord.com/developers/applications → **New Application** → name it.
3. **Bot** tab → **Reset Token** → copy it.
4. In the working folder, create a file named `.env` containing one line:
   `DISCORD_BOT_TOKEN=the-token-they-copied`
   If the folder is a git repo, add `.env` to `.gitignore`.
5. Run `check`; it prints an invite link. Open it, choose the server, approve, and wait for the
   "Success" page. If `check` still lists no servers, the invite didn't finish: in the Developer
   Portal check that **Installation → Guild Install** is ticked and **Bot → Requires OAuth2 Code
   Grant** is off, then invite again.

The token is a password to the bot. Tell the user to paste it only into the `.env` file themselves,
never into the chat. If they paste it in chat anyway, don't use it: tell them to reset it in the
Developer Portal and put the new one in `.env`. Never echo, log or write the token anywhere else.

The invite link asks for Administrator because creating private channels, roles and emojis needs
broad permissions, and partial permissions cause confusing "Missing Permissions" failures. Step 10
removes it afterwards.

### 3. Draft the blueprint

Copy the closest template from `assets/templates/` into the working folder (e.g. `my-server.json`)
as the skeleton, then reshape it with the niche playbook: swap in the signature channels, roles,
naming style and rules for this niche, add channels for the creator's big recurring series, and
use their audience's name for the member role. The template gives safe structure (START HERE,
staff area, permissions); the playbook and the creator's content give it personality.

| Template | Fits |
|---|---|
| `creator-community.json` | YouTubers, streamers, artists, newsletters - with a Supporter area |
| `gaming-community.json` | Gaming creators and clans - LFG, platform roles, squads, tournaments, bar-style names |
| `digital-products-support.json` | Selling courses, templates, software, AI skills - Customer-only area, tickets |
| `study-group.json` | Classes, exam prep, bootcamps, cohorts |
| `small-business.json` | Shops, cafés, salons, local services - VIP area, staff area |

What makes a good server, and why:

- **Fewer channels than you think (12-20).** A new server with 40 empty channels feels dead;
  people talk where other people are. Add channels later when one gets crowded.
- **START HERE at the top, read-only** (welcome, rules, announcements). New members read what's
  pinned there, and nobody can bury it under chat.
- **Roles express access, not decoration.** Every role should unlock something (a private
  category) or mean something (staff). Use `private_to` for paid/member/staff areas.
- **Always a private staff category** for moderators to coordinate and log actions.
- **Write real content, not placeholders**: a welcome message with 2-3 concrete first steps, short
  numbered rules with consequences, a FAQ answering the questions this audience actually has.
  Match the user's voice and language. Use `{server}` for the server name, `{#rules}` to link a
  channel (it also finds decorated names like `📜┃rules`), `{@Moderator}` to show a role (it never
  pings anyone) and `{:wave:}` to show one of the server's custom emojis.
  Leave a clearly marked `(add ...)` placeholder only for facts you can't know (opening hours,
  a payment link).
- **One naming style** throughout (plain, `💬・emoji-prefix`, `🎮┃bar` or lowercase words). Pick it
  from the playbook and the creator's tone.

### 4. Pick the bots (3-6, fewer is better)

Read `references/bots.md`. Start from what Discord already does (AutoMod, Onboarding, Events,
Server Subscriptions, Twitch/YouTube integrations), then pick only the bots this community needs,
each with a one-line reason tied to the content profile, e.g. "Streamcord - you stream on Twitch
most nights and fans want a go-live ping". Every extra bot is another dashboard and another set of
permissions, so leave out anything without a clear job.

Bots can't be added through the API: the user invites each one through its official website or the
Discord App Directory, never from a random link (look-alike scam bots exist). The catalog was
checked on the date it shows, so search quickly to confirm a bot is still running before
recommending it, especially music and alert bots.

Add what the chosen bots need to the blueprint now (bots.md has the table): `level-ups`,
`live-now`, `open-a-ticket`, a `Live Ping` role and so on, so each bot has its place on day one.

### 5. Safety, welcome and community systems

Read `references/community-systems.md` for the parts this community needs. It has the blueprint
blocks, defaults by niche and the text to give the user. Short version:

- **AutoMod (always add it):** an `automod` block with a level picked from the audience. Any
  audience mostly under 18 always gets `family-friendly`; most get `standard`; `relaxed` is only
  for adult, high-trust groups. Write niche `blocked_words`/`scam_words`, `allowed_words` for terms
  the niche needs, exempt the staff roles and channels, and send alerts to the staff `mod-log`.
  It runs on Discord's side, with no bot online.
- **Welcome:** `welcome.system_channel` for join messages, a `welcome.screen` (Community only), and
  `onboarding` questions that hand out ping/interest roles (Community only, and 7+ default
  channels to switch on). Per-member greetings ("Welcome @name, member #1,234") need a bot:
  write 2-3 greeting tones in the creator's voice and give that bot's setup steps.
- **Tickets:** with no bot, a `thread_only` channel plus `thread_staff` gives every member private
  threads only staff can see. For buttons and transcripts, use a ticket bot and write its panel text
  and niche-specific ticket categories.
- **Self-assign roles:** create ping roles (`Live Ping`, `Video Drops`, `Events`, `Giveaway Pings`)
  and interest roles with `none` permissions. Prefer onboarding questions. Otherwise post a
  `#get-roles` message with `reactions` for a reaction-role bot to use. Point alert bots at the ping
  roles, never @everyone.
- **Leveling:** 4-6 tier roles named for the niche; perks through a top-tier lounge
  (`private_to`) and images/links from tier 2 up (`media_to`). A leveling bot gives the roles.
- **Giveaways:** a read-only `giveaways` channel, the `Giveaway Pings` role, the announcement and
  short rules templates, and a giveaway bot. Tell the user that giveaway rules vary by country and
  the template isn't legal advice. Never suggest pay-to-enter, gambling-style or crypto-prize
  giveaways.

### 6. Emojis and stickers (optional)

Custom emojis and stickers make a community feel like its own place: the creator's face reactions,
mascot, catchphrases, inside jokes.

**Designing a branded set (6-10 emojis).** From the content profile, pick the creator's palette
(from their thumbnails, logo or channel art), their mascot or signature object, and 2-3
catchphrases or inside jokes. Plan a set that people will actually use in chat, for example:
hype/fire, laugh, sad, GG/thumbs up, "hmm"/thinking, heart, plus 2-4 that only make sense in this
community (the mascot waving, a catchphrase as a word-emoji, the series' signature item). Name them
short and lowercase (`hype`, `gg`, `mascot_wave`).

- **If this session has an image-generation tool**, generate each one as a single bold, simple
  shape with a thick outline, 2-3 colours from the palette, **a transparent background**, a centred
  square composition, and no small text (it must read at 32 px, and at 22 px inline). Generate at
  512 px or more; the pipeline resizes to 128 px. Show the set to the user before uploading, and
  regenerate any that look muddy when small.
- **Without an image tool**, give the user the same plan (name, idea, colours for each) and ask for
  the files, or suggest they commission an artist with it.
- **Only the creator's own branding.** Never draw other people's characters, logos, trademarks,
  game art or real people (except the creator, if they ask and it's their own likeness).

- **Where images come from**: the user's own files (logo, mascot, emotes they paid an artist for),
  images you generate for them with an image tool in this session, or packs with a clear licence
  that allows this use. **Don't download random memes or reaction images from the web** - they're
  almost always someone else's copyright, and many are photos of real people. If the user asks for
  "memes", offer to generate original ones in the creator's style instead.
- Put the files next to the blueprint (e.g. `emojis/hype.png`) and list them:
  ```json
  "emojis":   [{"name": "hype", "file": "emojis/hype.png"}],
  "stickers": [{"name": "GG", "file": "stickers/gg.png", "tags": "trophy", "description": "Good game!"}]
  ```
  Emoji names are 2-32 letters/numbers/underscores. Stickers need `tags` (the emoji they're
  suggested for) and a 2-30 character name.
- **Formats and limits**: emojis PNG/JPG/GIF/WebP up to 256 KB; stickers PNG/APNG/GIF exactly
  320x320 up to 512 KB (Lottie only on verified/partnered servers). `validate` checks every file;
  still images that are too big or the wrong size are resized automatically (stickers are padded
  to 320x320). Animated files that are too big must be compressed by the user, and the message
  explains how.
- **Slots** depend on the server's boost level: 50 static + 50 animated emojis and 5 stickers at
  level 0 (100/150/250 emojis and 15/30/60 stickers at levels 1/2/3). `inspect` shows what's
  free; anything over the limit is skipped with a clear message, never half-uploaded.

### 7. Show the plan and get approval

Run `validate` and fix any ERROR lines. Then run `preview BLUEPRINT` and show the user the HTML
mockup: it looks like Discord's sidebar, with categories, channel icons, locks on private areas,
coloured roles, the emoji strip and the welcome post. Open it in the browser if the session can,
otherwise give the file path. Also show the printed layout (roles, categories, channels, who can
see what, emojis, stickers), the bot picks with their reasons, and the `health BLUEPRINT` score
with anything still worth fixing. Briefly
mention what each private area is for. Wait for their OK - this changes their real server, and
it's much easier to change a JSON file than to undo 20 channels.

### 8. Dry run, then apply

After a real `apply`, the script scores the live server automatically (pass `--no-health` to
skip it). Put the score and its top 2-3 fixes in the final report. Each fix names the blueprint
change or command that solves it. `health --guild ID` re-checks any time, e.g. a month later, when
it also flags channels nobody has used in 30 days.

1. `check` - pick the right server ID from the list.
2. `apply ... --dry-run` - shows what will be created vs. what already exists.
3. `apply ...` - creates roles, emojis and stickers, then categories and channels with
   permissions, then posts and pins starter messages. Report the summary line and any `!` problems.

Applying is safe to repeat: anything that already exists (same name, same place) is skipped and no
duplicate messages are posted. Plain `apply` never edits or deletes anything.

#### Editing an existing server (`--update`)

When the user wants changes ("rename general to hangout", "make the clips channel members-only",
"move off-topic down", "rewrite the rules"), edit the blueprint and run
`apply --update --dry-run`. It lists every difference:

- `+` new items, `~` changes, `-` deletions, and `i` notes for things it refuses to touch.
- **Rename** by giving the new `name` plus `"was": "old name"` (works for channels, categories,
  roles, emojis and stickers). Without `was`, a new name means a new item.
- **Changes it applies**: topic, slowmode, voice user limit, moving a channel to another category,
  who can see/post (`private_to`, `read_only`, `writers`), role colour/permissions/hoist/
  mentionable, the order of categories, channels and roles (it follows the blueprint), the
  text of the bot's own starter posts (edited in place, so there are no duplicates), the `SB · `
  AutoMod rules, join-message settings, the welcome screen and onboarding questions.
- **What it leaves alone**: permission rules for roles the blueprint doesn't mention (another
  bot's, or ones the owner set by hand), @everyone itself, roles managed by bots or integrations,
  roles at or above the bot's own role, forum starter posts, and anything not in the blueprint.
  It never removes Administrator from an existing role.

Show the user the change list, get a yes, then run it without `--dry-run`. Edits aren't recorded for
`undo`, so the dry-run list is the record of what changed.

#### Deleting

Deleting can't be undone, and messages inside a deleted channel are lost. So:

1. Put exactly what the user named in the blueprint's `"remove": {"channels": [...], "roles": [...],
   "emojis": [...], "stickers": [...], "automod": [...]}` and run `apply --update --dry-run`, or for one-off cleanups
   use `delete --guild ID --channel "name" ...`. Both only list what would go.
2. Show the user that exact list and get a clear yes.
3. Re-run with `--confirm-delete`.

It refuses anything ambiguous (two channels with the same name), @everyone, managed roles and roles
above the bot. Deleting a category keeps its channels; they move out of the category. Never add
items to `remove` that the user didn't ask to delete.

`undo BLUEPRINT.result.json` removes everything earlier applies of that blueprint created
(channels, roles, emojis, stickers, AutoMod rules) and leaves what was already there. Join-message,
welcome-screen and onboarding settings aren't undone; change them with `--update`. Run it with `--dry-run`
first and confirm with the user too.

### 9. Common problems

| Message | Fix |
|---|---|
| token was rejected | Reset the token in the Developer Portal, update `.env` |
| Missing permissions | Re-invite with the `check` link; in Server Settings → Roles drag the bot's role to the top |
| Not found | The bot isn't in that server, or the ID is wrong - run `check` |
| "...creating as text/voice" | Community isn't enabled; see step 10, then convert the channel in its settings |
| "not changed (at or above the bot's own role)" | Drag the bot's role above that role, then run the update again |
| "emoji/sticker slots are used" | Delete unused ones, boost the server, or upload fewer |
| "Discord allows 1 ... rule(s) and the server already has ..." | The server has its own AutoMod rule of that type; edit or delete it in Server Settings → AutoMod, then re-run |
| "onboarding needs 7+ default channels" | Add more default channels to `onboarding.default_channels` (each must be visible to everyone) |

### 10. Finish the setup (things the bot should not do)

Give the user this short checklist, trimmed to what applies:

- **Invite the chosen bots** from their official links and set each one up in the channel made for
  it. If a bot must post in a read-only channel (like `level-ups`), add the role Discord created
  for it (usually the bot's name) to that channel's `writers` and run `apply --update`.
- **Enable Community** (Server Settings → Enable Community) to unlock announcement channels,
  forums, stages, onboarding and the welcome screen. Without it, those were created as text/voice.
- **Server icon and banner** for recognition in the server list.
- **Safety**: Server Settings → Safety Setup → set the verification level to at least Medium
  (High for teen audiences). The `SB · ` AutoMod rules are already on; check they fit after a week.
- **Remove the bot's Administrator** once setup is done (Server Settings → Roles → the bot's role),
  or kick it if no more changes are planned. A bot with admin rights is a risk if its token leaks.
- **Give people roles**: right-click a member → Roles, or let the paid-role bot do it.
- **Invite link**: Server name → Invite People → Edit → never expire, and link it from #welcome,
  bios and video descriptions.
- **Rituals for week one** from the playbook (game night, weekly prompt, clip of the week).

## Blueprint reference

```json
{
  "server_name": "My Server",
  "roles": [
    {"name": "Admin", "color": "#E74C3C", "hoist": true, "permissions": "admin"},
    {"name": "Member", "permissions": "member"},
    {"name": "Patron", "was": "Supporter", "permissions": "member"}
  ],
  "emojis":   [{"name": "hype", "file": "emojis/hype.png"}],
  "stickers": [{"name": "GG", "file": "stickers/gg.png", "tags": "trophy", "description": "Good game!"}],
  "channels": [ { "name": "uncategorized-channel" } ],
  "categories": [
    {
      "name": "📌 START HERE",
      "read_only": true, "writers": ["Admin"],
      "channels": [
        {"name": "welcome", "topic": "...", "message": "Welcome to {server}! Read {#rules} {:hype:}", "pin": true},
        {"name": "announcements", "type": "announcement"}
      ]
    },
    {"name": "💬 CHAT", "channels": [
        {"name": "get-roles", "message": "🔴 {@Live Ping}  🎁 {@Giveaway Pings}", "reactions": ["🔴", "🎁"]},
        {"name": "clips", "media_to": ["Level 5", "Moderator"]},
        {"name": "open-a-ticket", "thread_only": true, "thread_staff": ["Moderator"], "message": "How to open a ticket..."}
    ]},
    {"name": "🔒 MEMBERS", "private_to": ["Member", "Admin"], "channels": [{"name": "members-chat"}]}
  ],
  "automod": {"level": "standard", "alert_channel": "mod-log", "exempt_roles": ["Moderator", "Admin"],
              "blocked_words": [], "allowed_words": [], "scam_words": []},
  "welcome": {"system_channel": "general", "join_messages": true, "boost_messages": true,
              "screen": {"description": "...", "channels": [{"channel": "rules", "description": "Read first", "emoji": "📜"}]}},
  "onboarding": {"default_channels": ["welcome", "rules", "general", "..."],
                 "questions": [{"title": "What do you want pings for?",
                                "options": [{"title": "Going live", "emoji": "🔴", "roles": ["Live Ping"]}]}]},
  "remove": {"channels": ["old-channel"], "roles": [], "emojis": [], "stickers": [], "automod": []}
}
```

- **Roles**: list them highest first; the order is kept on create and enforced by `--update`.
  `permissions` is `none` (badge/access-only), `member`, `moderator` (manage messages, timeout,
  kick), `admin` (manage server/roles/channels/expressions, but *not* the Administrator flag), or a
  list of permission names such as `["VIEW_CHANNEL", "SEND_MESSAGES"]`. `hoist` shows the role
  separately in the member list.
- **Channel types**: `text` (default), `voice`, `announcement`, `forum`, `stage`.
  Forum posts use `message_title` + `message` as the first post. Voice accepts `user_limit`.
  Text accepts `topic`, `slowmode` (seconds), `message`, `pin`.
- **Access** (set on a category, overridable per channel): `private_to: [roles]` means only these
  roles see it; `read_only: true` + `writers: [roles]` means everyone can read but only writers
  post; `thread_only: true` + `thread_staff: [roles]` makes a private-thread ticket channel;
  `media_to: [roles]` lets only those roles post images and link previews. A channel inherits its
  category's access unless it sets the same key.
- **`reactions`** on a channel with a `message`: the bot adds these reactions to its starter post
  (unicode emojis, or `{:name:}` for server emojis), ready for a reaction-role bot.
- **`automod`, `welcome`, `onboarding`**: see `references/community-systems.md`.
- **`was`** on any item renames it during `--update`. **`remove`** only acts with
  `--update --confirm-delete`.
- **`language`**: the blueprint's language code; see `references/languages.md`.
- **Sharing**: `export --guild ID OUT.json` produces a blueprint without IDs, members, message
  authors or invite links (permissions become role names, starter posts keep their text, and
  emoji images aren't included). Blueprints never grant Administrator and may only point at files
  inside their own folder. Community blueprints live in `blueprints/`; see its README.
- A `<blueprint>.result.json` log next to the blueprint collects the IDs of everything created
  across runs; `undo` uses it.
