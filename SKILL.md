---
name: discord-server-builder
description: Designs, builds and maintains a complete Discord server - roles, categories, channels, private and read-only areas, starter posts (welcome, rules, FAQ), custom emojis and stickers - in the user's real server through a bot, and recommends the few bots that best fit the community. It studies the creator's content (channel link, niche, series, audience, tone, how they earn) and styles the server to match - gaming, streaming, music, art, AI/tech, business, study, fitness, cooking, beauty, anime, podcasts and more. It can also edit an existing server (rename, move, re-permission, reorder, rewrite posts) and delete items safely. Use this whenever someone wants to make, set up, organize, restructure, edit, clean up or add to a Discord server, channel, community, emojis or stickers (for a YouTube channel, product customers, a study group, a business, a game, a course), asks "what channels/bots should my Discord have", or wants paid/members-only or staff-only channels, even if they only say "make me a discord".
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
| `delete --guild ID --channel N --role N --emoji N --sticker N` | Lists those items; deletes only with `--confirm-delete` |
| `undo BLUEPRINT.result.json [--dry-run]` | Deletes exactly what earlier applies created |

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
broad permissions, and partial permissions cause confusing "Missing Permissions" failures. Step 8
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

### 5. Emojis and stickers (optional)

Custom emojis and stickers make a community feel like its own place: the creator's face reactions,
mascot, catchphrases, inside jokes.

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

### 6. Show the plan and get approval

Run `validate`, fix any ERROR lines, and show the user the printed layout (roles, categories,
channels, who can see what, emojis, stickers) plus the bot picks with their reasons. Briefly
mention what each private area is for. Wait for their OK - this changes their real server, and
it's much easier to change a JSON file than to undo 20 channels.

### 7. Dry run, then apply

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
  mentionable, the order of categories, channels and roles (it follows the blueprint), and the
  text of the bot's own starter posts (edited in place, so there are no duplicates).
- **What it leaves alone**: permission rules for roles the blueprint doesn't mention (another
  bot's, or ones the owner set by hand), @everyone itself, roles managed by bots or integrations,
  roles at or above the bot's own role, forum starter posts, and anything not in the blueprint.
  It never removes Administrator from an existing role.

Show the user the change list, get a yes, then run it without `--dry-run`. Edits aren't recorded for
`undo`, so the dry-run list is the record of what changed.

#### Deleting

Deleting can't be undone, and messages inside a deleted channel are lost. So:

1. Put exactly what the user named in the blueprint's `"remove": {"channels": [...], "roles": [...],
   "emojis": [...], "stickers": [...]}` and run `apply --update --dry-run`, or for one-off cleanups
   use `delete --guild ID --channel "name" ...`. Both only list what would go.
2. Show the user that exact list and get a clear yes.
3. Re-run with `--confirm-delete`.

It refuses anything ambiguous (two channels with the same name), @everyone, managed roles and roles
above the bot. Deleting a category keeps its channels; they move out of the category. Never add
items to `remove` that the user didn't ask to delete.

`undo BLUEPRINT.result.json` removes everything earlier applies of that blueprint created
(channels, roles, emojis, stickers) and leaves what was already there. Run it with `--dry-run`
first and confirm with the user too.

### 8. Common problems

| Message | Fix |
|---|---|
| token was rejected | Reset the token in the Developer Portal, update `.env` |
| Missing permissions | Re-invite with the `check` link; in Server Settings → Roles drag the bot's role to the top |
| Not found | The bot isn't in that server, or the ID is wrong - run `check` |
| "...creating as text/voice" | Community isn't enabled; see step 9, then convert the channel in its settings |
| "not changed (at or above the bot's own role)" | Drag the bot's role above that role, then run the update again |
| "emoji/sticker slots are used" | Delete unused ones, boost the server, or upload fewer |

### 9. Finish the setup (things the bot should not do)

Give the user this short checklist, trimmed to what applies:

- **Invite the chosen bots** from their official links and set each one up in the channel made for
  it. If a bot must post in a read-only channel (like `level-ups`), add the role Discord created
  for it (usually the bot's name) to that channel's `writers` and run `apply --update`.
- **Enable Community** (Server Settings → Enable Community) to unlock announcement channels,
  forums, stages, onboarding and the welcome screen. Without it, those were created as text/voice.
- **Server icon and banner** for recognition in the server list.
- **Safety**: Server Settings → Safety Setup → set the verification level to at least Medium and
  turn on AutoMod spam/keyword filters.
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
    {"name": "🔒 MEMBERS", "private_to": ["Member", "Admin"], "channels": [{"name": "members-chat"}]}
  ],
  "remove": {"channels": ["old-channel"], "roles": [], "emojis": [], "stickers": []}
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
  post. A channel inherits its category's access unless it sets the same key.
- **`was`** on any item renames it during `--update`. **`remove`** only acts with
  `--update --confirm-delete`.
- A `<blueprint>.result.json` log next to the blueprint collects the IDs of everything created
  across runs; `undo` uses it.
