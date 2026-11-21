# Discord Server Builder: a Claude skill

Tell Claude what your community is about and it builds the whole Discord server for you, inside your real server, in minutes.

> "Make a Discord for my cooking channel with a paid members area."

Claude studies your content (niche, series, audience, tone, how you earn), designs a server that fits, shows you the plan, and then creates it:

- **Roles and permissions**: admins, moderators, members, paid or customer roles, set up correctly
- **Categories and channels**: text, voice, announcements, forums, stage, private and read-only areas
- **Starter posts**: welcome, rules and FAQ written in your voice, pinned where they belong
- **Custom emojis and stickers**: checked against Discord's size and slot limits, auto-resized when needed
- **AutoMod**: Discord's built-in filter set up for your audience (family-friendly, standard or relaxed), with scam-link, invite, mention-spam and niche word rules; runs with no bot online
- **Welcome**: join messages, the Community welcome screen, and onboarding questions that hand out roles, plus greeting texts for a welcome bot
- **Tickets without a bot**: a private-thread support channel only staff can see, or setup steps for a ticket bot
- **Self-assign and ping roles**: onboarding questions or a ready `#get-roles` post with reactions for a reaction-role bot
- **Leveling and giveaways**: tier roles named for your niche, perks like top-tier lounges and image permissions, a giveaways channel, ping role and rules template
- **Bot recommendations**: the 3–6 bots that best fit *your* community, with invite links and setup steps
- **Server Health Score**: rates a planned or live server 0–100 (structure, safety, privacy, engagement, clarity) with a concrete fix for every problem; runs automatically after each build
- **Visual preview**: a Discord-style HTML mockup of the layout before anything is created
- **Branded emojis**: designs a 6–10 emoji set in your colours and style (generated if your session has an image tool), then resizes, checks and uploads it
- **Any language**: channel names, rules, posts and filters written natively (Spanish, Portuguese, Hindi, Japanese, Arabic with right-to-left preview, French, German, Indonesian and more)
- **Share and reuse layouts**: export a live server as a clean blueprint (no IDs, members or invite links) and install community blueprints from [`blueprints/`](blueprints)
- **Editing later**: rename, move, re-permission, reorder and rewrite posts; it shows a change list first
- **Safe deletes and undo**: nothing is deleted without your explicit confirmation

Styles for gaming, streaming, music, art, AI/tech, business, study, fitness, cooking, beauty, anime, podcasts and more. Templates included: creator community, gaming community, digital-product customers, study group, small business.

## Install

```bash
npx skills add Nyxiflare/discord-server-builder
```

Or copy this folder to `~/.claude/skills/discord-server-builder`.

## Quick start

1. Create a server in Discord (or use an existing one).
2. Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications) → **Bot** → **Reset Token**.
3. Put the token in a file called `.env` in your working folder:
   ```
   DISCORD_BOT_TOKEN=your-token-here
   ```
   Never paste the token into a chat or commit it. This repo's `.gitignore` already excludes `.env`.
4. Ask Claude: *"Set up my Discord server for my YouTube channel about ..."*

Claude gives you the bot's invite link, shows you a preview of the layout, runs a dry run, and builds the server only after you approve.

## Ready-made blueprints

Say *"Use the podcast-community blueprint for my server"* and Claude adapts it to you. Blueprints in
[`blueprints/`](blueprints): indie game dev, podcast community, fitness challenge. The templates
in `assets/templates` (creator, gaming, digital products, study group, small business, Spanish
creator community) work the same way. To share your own server's layout, run `export` and open a
pull request; [blueprints/README.md](blueprints/README.md) explains how.

## Requirements

- Claude Code (or any agent that supports skills)
- Python 3.9+ (standard library only; Pillow is optional, for auto-resizing emoji images)

## What still needs a bot

The skill builds the structure. A few things only work with an always-online bot, and the skill
recommends one and writes its setup for you: per-member welcome greetings, ticket button panels,
classic emoji reaction roles, XP leveling, and running giveaway draws. Welcome screen and
onboarding need Discord's Community setting turned on.

## Safety

- The token is read from `.env` and never printed.
- `apply` only creates things unless you pass `--update`. Deletes need `--confirm-delete`.
- Every run can be previewed with `--dry-run`, and `undo` removes exactly what a run created.
- After setup, you can remove the bot's Administrator permission.

## License

MIT. See [LICENSE](LICENSE).
