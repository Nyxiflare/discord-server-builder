# Community systems: AutoMod, welcome, tickets, self-roles, leveling, giveaways

What the script builds directly, what needs a bot, and the text to give the user. Read only the
sections the community needs. Bot names, links and status are in `bots.md`.

**Contents:** 1 AutoMod · 2 Welcome · 3 Tickets · 4 Self-assign roles · 5 Leveling · 6 Giveaways

| System | Built by the script (no bot) | Needs an always-online bot for |
|---|---|---|
| AutoMod | All rules (`automod` block) | Raids, new-account gates, warn/strike systems |
| Welcome | Join-message channel, welcome screen*, onboarding*, pinned posts | Personal greetings ("Welcome @name, member #1,234"), DMs, welcome images |
| Tickets | Private-thread ticket channel (`thread_only`) | Button panels, transcripts, ticket categories |
| Self-roles | Onboarding questions*, the `#get-roles` post with reactions | Classic emoji-reaction roles |
| Leveling | Tier roles, perks (`private_to`, `media_to`), `#level-ups` | Counting XP and giving the roles |
| Giveaways | `#giveaways` channel, `Giveaway Pings` role, rules text | Running the draw |

\* Only once Community is enabled; otherwise the script skips it and says so.

---

## 1. AutoMod

Discord's own filter runs on Discord's servers, so it works with no bot online. Add an
`automod` block; the script creates up to 5 rules named `SB · ...`:

```json
"automod": {
  "level": "standard",
  "alert_channel": "mod-log",
  "exempt_roles": ["Moderator", "Admin"],
  "exempt_channels": ["mod-chat", "mod-log"],
  "blocked_words": ["niche-specific", "words", "or phrases*"],
  "allowed_words": ["words the niche uses that filters wrongly catch"],
  "scam_words": ["extra scam phrases for this niche"],
  "allowed_links": ["youtube.com", "twitch.tv"],
  "max_mentions": 8,
  "block_message": "Blocked by the server filter. Wrong? Ask a moderator."
}
```

| Rule | family-friendly | standard | relaxed |
|---|---|---|---|
| Slurs & adult content (Discord's preset lists) | profanity + sexual + slurs | sexual + slurs | slurs |
| Scams, invites & spam links | scam phrases + look-alike domains + **all invites + all links** (creator platforms allowed) + 1 h timeout | scam phrases + invites + 1 h timeout | scam phrases only |
| Blocked words | the niche list, if any | same | same |
| Mention spam | 5 mentions, raid protection, 10 min timeout | 8 | 15 |
| Spam (Discord's spam detection) | on | on | on |

**Choosing the level** from the content profile:
- **family-friendly**: any audience that's mostly under 18 (always), kids and family, education,
  Roblox/Minecraft/Fortnite-style gaming, faith and wellness.
- **standard**: most creators, businesses, product sellers, adult gaming.
- **relaxed**: adult communities where swearing is normal and trust is high (small friend
  groups, adult comedy or commentary). Never relaxed for crypto/finance; scams target them first.

**Niche word lists.** Write `blocked_words` and `scam_words` for this niche. Examples:
- Gaming: free vbucks/robux, account selling, boosting, cheat/aimbot sellers.
- Crypto/finance: airdrop, guaranteed returns, "DM me to invest", seed phrase, wallet connect.
- Product sellers: cracked/leaked copies of their product, "cheaper on telegram".
- Study: paid assignment/essay services, "exam answers".
Use `allowed_words` for words the niche needs that filters catch, e.g. gaming's
"kill/shoot/headshot", or medical/fitness anatomy terms. Keyword rules match whole words; put
`*` at the end of an entry to match word stems.

**Limits:** Discord allows 6 keyword rules and 1 each of spam, preset, mention-spam and
member-profile rules per server, with up to 1000 keywords, 10 regex patterns and 100 allow-list
entries per rule. If the server already has its own rule of a type (Discord's Safety Setup adds
"Block Mention Spam" and "Commonly Flagged Words"), the script skips ours and names the existing
rule so the user can decide.

**What AutoMod can't do** (recommend a moderation bot from `bots.md` if needed): stop coordinated
raids (Wick), keep out brand-new or alt accounts (Wick, Double Counter-type bots), warn/strike
systems with automatic escalation (Dyno, Carl-bot), or log deleted and edited messages (Dyno,
Carl-bot).

Also tell the user to set **Server Settings → Safety Setup → Verification level** (Medium or
higher; High for teen audiences). The script doesn't change that setting.

## 2. Welcome

The script can set:
```json
"welcome": {
  "system_channel": "general",
  "join_messages": true, "join_sticker_replies": true, "boost_messages": true, "setup_tips": false,
  "screen": {"description": "One line about the community (140 max)",
             "channels": [{"channel": "rules", "description": "Read first", "emoji": "📜"}]}
}
```
- `system_channel` is where Discord's own "X joined" and boost messages appear. Plain `apply` only
  sets it if the server has none; `--update` moves it.
- `screen` is the **welcome screen** new members see (Community only): up to 5 channels, each with
  a short description (50 max) and an emoji (unicode, or `{:name:}` for a server emoji).
- `onboarding` (section 4) shows questions when people join.
- The pinned `#welcome` post: write 2-3 concrete first steps in the creator's voice.

**Personal greetings need a bot.** Messages like "Welcome @name, you're member #1,234!", welcome
DMs and welcome images need a bot that's always online. This script isn't one. So:
1. Pick one welcome bot from `bots.md` (usually the all-rounder already chosen, e.g. Carl-bot or
   MEE6, so the server doesn't need an extra bot).
2. Write the greeting in the creator's voice and offer 2-3 tones:
   - **Hype**: "🎉 {user} just landed in {server}! You're member #{count}. Grab your roles in #get-roles and say hi!"
   - **Cozy**: "Welcome in, {user} ☕ Make yourself at home: #introductions is a good first stop."
   - **Professional**: "Welcome to {server}, {user}. Start with #rules and #faq; our team is in #help if you need us."
3. Before giving setup steps, **look up that bot's current variable syntax** (it differs: some use
   `{user}`, others `{user.mention}` or `{mention}`, and `{server.member_count}` vs
   `{membercount}`) and rewrite the placeholders to match. Then give click-by-click steps: the
   dashboard page, which channel (the one the skill created), and whether to also DM.
4. Keep only one greeting source: if a bot posts greetings, set `"join_messages": false` so
   members don't get two welcomes.

## 3. Tickets

**Path A, no bot (default for small servers, or when the user doesn't want more bots):**
private threads. The script builds it with:
```json
{"name": "open-a-ticket", "thread_only": true, "thread_staff": ["Support Team", "Moderator"],
 "pin": true, "message": "how to open a ticket..."}
```
Members can read the channel and open **private threads** but can't chat in it. A private thread
is visible only to its opener, people they add, and roles with Manage Threads, which
`thread_staff` gets. Add a staff-only `ticket-log` channel and a `Support Team` role. The pinned
post must explain the steps: Threads button (or +) → Private Thread → name it → describe.
Downsides to mention: there's no button or transcript, and members need to know how to open a
private thread.

**Path B, ticket bot (bigger servers, product sellers, anyone who wants buttons and transcripts):**
recommend Ticket Tool (see `bots.md`) and give:
- **Panel text** in the creator's voice, e.g. "Need help? Pick a reason below and a private
  ticket opens just for you and our team."
- **Ticket categories from the content profile**:
  - Product seller: Order issue · Refund · Download/licence problem · Pre-sales question
  - Creator: Brand/collab inquiry · Report a member · Ban appeal · Other
  - Business: Order/booking problem · Complaint · Wholesale/partnership
  - Gaming: Report a player · Tournament question · Appeal
- **Setup**: the panel goes in `#open-a-ticket` (make it `read_only` with the bot's role in
  `writers`, or rely on the bot's admin), transcripts go in `#ticket-log`, and the staff role is the
  one the skill created.

## 4. Self-assign roles (reaction roles)

Create the roles first, all with `"permissions": "none"`, and `"mentionable": true` for ping roles:
- **Ping roles**: `Live Alerts`/`Live Ping`, `Video Drops`, `Events`, `Giveaway Pings`, `Product
  Updates`. Connect them to the alert bots chosen earlier, e.g. tell the YouTube alert bot to ping
  `@Video Drops`, never @everyone.
- **Interest roles** from the content profile (games, platforms, genres, subjects, regions).
- **Pronoun roles** only if the community would want them.

**Path A, native (preferred once Community is on):** onboarding questions, built by the script:
```json
"onboarding": {
  "default_channels": ["welcome", "rules", "general", "..."],
  "questions": [{"title": "What do you want pings for?", "options": [
     {"title": "Going live", "emoji": "🔴", "roles": ["Live Ping"]},
     {"title": "Giveaways", "emoji": "🎁", "roles": ["Giveaway Pings"], "channels": ["giveaways"]}]}]
}
```
Onboarding only switches on with **7 or more default channels**; with fewer, the questions are
saved and it stays off, and the script says so. Members can change their answers later in
Channels & Roles.

**Path B, reaction-role bot (Community off, or the user wants the classic message):** the
script posts the `#get-roles` message and adds the reactions itself (`"reactions": ["🔴",
"{:hype:}"]` on the channel). The user then links each emoji to its role in the bot (Carl-bot:
dashboard → Reaction Roles → pick the existing message in `#get-roles` → add the emoji → role
pairs). Write the message so each line shows the emoji, the `{@Role}` and what the ping is for.

## 5. Leveling

There's no native leveling, so a bot counts XP. The skill builds the structure:
- **4-6 tier roles** named for the niche and tone, highest first, hoisting only the top 1-2:
  | Niche | Tiers (low → high) |
  |---|---|
  | Gaming | Rookie → Grinder → Pro → Elite → Legend |
  | Study / education | Freshman → Sophomore → Scholar → Mentor → Professor |
  | Music | Listener → Beatmaker → Producer → Headliner → Legend |
  | Art | Sketcher → Illustrator → Artist → Master |
  | Fitness | Beginner → Regular → Athlete → Beast → Champion |
  | Business | Starter → Builder → Operator → Founder |
  | Anime / fandom | Newbie → Otaku → Senpai → Sensei |
  | Cooking | Taster → Home Cook → Chef → Head Chef |
- **Perks through channels, not permissions**: a private lounge for the top tiers
  (`private_to`), and **images/links only from tier 2 up** in busy channels (`"media_to": [tier
  roles + staff]`). This stops brand-new spam accounts from posting links and images.
- A `level-ups` channel (read-only; add the bot's role to `writers` after inviting it), or tell the
  bot to send level-ups by DM so chat stays quiet.

Bot setup steps to give (adapt to the bot, `bots.md` has which ones charge for role rewards):
- **XP**: default rate, with a 60-second cooldown and messages under ~5 words ignored (stops
  farming).
- **No-XP channels**: bot commands, memes/spam-prone channels, staff channels, `#level-ups`, counting games.
- **Level → role**: e.g. level 5 Grinder, 15 Pro, 30 Elite, 50 Legend, with "remove previous tier" on.
- **Level-up message** in the creator's voice using that bot's variables, e.g. "🔥 {user} just hit
  level {level}! Keep it up." (check the bot's syntax first).

## 6. Giveaways

The skill builds: a `giveaways` channel (read-only for members, who still enter by reaction or
button), a `Giveaway Pings` role tied into self-roles, and the texts below. A bot runs the draw:
**GiveawayBot** for simple ones (`/gcreate` for guided setup, `/gstart <time> <winners>
<prize>`, `/greroll` to pick a new winner), or **Apollo** when entry rules are needed (required
role, level from the leveling system, minimum account age, time in the server). Entry rules stop
alt-account farming.

**Announcement template:**
> 🎁 **GIVEAWAY: [prize]**
> Enter by pressing the button below. Ends **[date, time, timezone]**. [N] winner(s).
> Requirements: [e.g. Grinder role or higher, in the server 7+ days].
> {@Giveaway Pings} · Official rules in the thread below.

**Short official rules template** (fill in the brackets; not legal advice):
1. **No purchase necessary.** Buying anything doesn't improve your chances.
2. **Eligibility**: [age, e.g. 18+ or 13+ with parental permission], [regions], must follow
   Discord's Terms and the server rules; staff and their households can't enter.
3. **Dates**: starts [date/time/timezone], ends [date/time/timezone].
4. **How winners are picked**: at random by [bot name] from valid entries after the end time.
5. **How winners are contacted**: in this channel and by a staff member's DM. Staff will **never**
   ask for passwords, payment details or a fee.
6. **Claiming**: the winner must reply within [48 hours], or a new winner is drawn.
7. **Prize delivery**: [how and when, e.g. a gift code by DM within 7 days]. No cash alternative.
8. **Disqualification**: alt accounts or breaking the rules voids an entry.
9. Organised by [creator/server], not by Discord.

Tell the user: rules for giveaways and contests differ by country (some require registration,
bonding or restrict who can enter, especially for real-money or high-value prizes). They should
check the rules where they and their audience live, and get advice for anything valuable. Don't
suggest giveaways that need payment or purchase to enter, gambling-style mechanics (paid spins,
loot boxes, "buy entries"), or crypto/token/NFT prizes.
