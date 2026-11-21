# Recommended bots

Last checked: **2026-11-21** with web searches (mostly 2026 roundups and vendor pages; prices and
free tiers change often). Before recommending a bot, run a quick search to confirm it's still
running, especially music and alert bots, which shut down often. Update this date when you re-check.

## How to choose

1. **Use Discord's built-in features first.** Each one is a bot the server doesn't need:
   | Need | Built in (Server Settings) |
   |---|---|
   | Spam/keyword filtering | **AutoMod** (Safety Setup) |
   | Welcome questions and auto-roles on join | **Onboarding** (needs Community) |
   | Events with RSVPs | **Events** (Scheduled Events) |
   | Paid membership roles | **Server Subscriptions** (where available) |
   | Twitch subscriber roles / YouTube member roles | **Integrations** → connect Twitch or YouTube |
   | Polls | the built-in **/poll** (Send Polls permission) |
2. **Then 3-6 bots at most.** Every extra bot is another dashboard to learn, another set of
   permissions, and more noise. One all-rounder (Carl-bot, Dyno or MEE6) often covers moderation,
   reaction roles, welcome messages and logs together.
3. **Tie each pick to the creator's content** in one line, e.g. "Streamcord, because you stream on
   Twitch 4 nights a week and fans want a ping".

## Catalog

**Status column:** ✅ = seen active in 2026 sources. ⚠️ = couldn't confirm in the check above, so
search before recommending.

### Moderation & security
| Bot | Good for | Cost | Website | Asks for |
|---|---|---|---|---|
| Carl-bot | All-rounder: reaction roles, automod, logs, welcome, embeds. Best single default | Free; premium about $5/mo | carl.gg | Administrator by default (can be reduced) |
| Dyno | Long-trusted moderation, automod, timed mutes/bans, logs, custom commands | Free; premium | dyno.gg | Manage roles/messages, kick/ban |
| Wick | Anti-raid / anti-nuke protection for big or targeted servers | Free; premium | wickbot.com | Administrator (needs it to undo raids) |
| MEE6 | Popular all-rounder with leveling; many features are behind premium | Free; premium about $12/mo | mee6.xyz | Administrator by default |

✅ all four (2026 roundups). Pick **one** all-rounder, and add Wick only for large or high-risk servers (crypto, big creators).

AutoMod (built in, set up by the script) covers word filters, scam links, mention spam and spam.
These bots add what AutoMod can't: raid/anti-nuke protection and alt-account gates (Wick),
warn/strike escalation and deleted-message logs (Dyno, Carl-bot). See `community-systems.md` §1.

### Welcome & greetings
| Bot | Good for | Cost |
|---|---|---|
| Carl-bot | Welcome message in a channel and/or DM, leave messages, embeds | Free |
| MEE6 | Welcome message + welcome card image | Welcome free; cards and extras premium |
| Dyno | Simple welcome/leave messages | Free |

✅ all three. Use the all-rounder that's already in the server rather than adding a welcome-only
bot. Variable syntax differs between bots, so check it before writing the setup steps. Greeting
texts and tone variants are in `community-systems.md` §2.

### Reaction roles / self-assign roles
Carl-bot (above) is the usual choice. Use the built-in **Onboarding** instead when Community is
on. The script can post the `#get-roles` message and add its reactions, so the bot only needs the
emoji → role links (`community-systems.md` §4).

### Tickets / support
| Bot | Good for | Cost | Website | Asks for |
|---|---|---|---|---|
| Ticket Tool | Private support tickets from a button panel; transcripts | Free; premium | tickettool.xyz | Manage channels/roles |
| Tickets (TicketsBot) | Same job, clean dashboard | Free; premium | tickets.bot | Manage channels/roles |

✅ Ticket Tool. ⚠️ Tickets: confirm it before recommending. For a no-bot option (private threads)
and ticket categories by niche, see `community-systems.md` §3.

### Leveling / XP
| Bot | Good for | Cost | Website | Asks for |
|---|---|---|---|---|
| Arcane | Leveling with role rewards; also automod and giveaways | Free; voice XP and advanced features are premium | arcane.bot | Manage roles, send messages |
| MEE6 | Leveling + rewards (if MEE6 is already the all-rounder) | Rewards mostly premium | mee6.xyz | as above |

✅ both. Tier names, perks and XP settings are in `community-systems.md` §5.

### Stream & upload alerts (YouTube / Twitch / TikTok / Kick)
| Bot | Good for | Cost | Website | Asks for |
|---|---|---|---|---|
| Streamcord | Twitch go-live alerts, live roles | Free tier limits the number of streamers; premium | streamcord.io | Send messages, manage roles |
| MEE6 / Carl-bot feeds | YouTube/Twitch alerts if one is already installed | Some feeds are premium | see above | — |
| Pingcord, NotifyMe | YouTube / TikTok / Kick alerts | Free tiers | official sites | Send messages |

✅ Streamcord. ⚠️ Pingcord and NotifyMe weren't confirmed. Search before recommending; for TikTok alerts in particular, confirm the bot still supports TikTok.

### Events & scheduling
| Bot | Good for | Cost | Website |
|---|---|---|---|
| Apollo | RSVPs, recurring events (free up to a limit), sign-up limits, giveaways too | Free; premium | apollo.fyi |
| Sesh | Calendar-first: time zones, reminders, polls to pick a time; recurring events are premium | Free; premium | sesh.fyi |

✅ both. Simple one-off events: use the built-in Events instead.

### Giveaways
| Bot | Good for | Cost | Website |
|---|---|---|---|
| GiveawayBot | Simple slash-command giveaways: `/gcreate` (guided), `/gstart <time> <winners> <prize>`, `/greroll` | Free | giveawaybot.party |
| Apollo | Giveaways with entry rules (account age, roles, server tenure, message count), rerolls, history | Free; premium | apollo.fyi |

✅ both. Use Apollo when entry rules are needed to stop alt accounts. Announcement and rules
templates are in `community-systems.md` §6.

### Paid membership roles
| Tool | Good for | Fee (verify on their pricing page) | Website |
|---|---|---|---|
| Patreon | Creators already on Patreon; tier → role sync is built in | Patreon's platform fee (about 8-12%) | patreon.com (Creator settings → Discord) |
| Whop | Selling access, digital products and memberships; auto role sync | About 3% + $0.30 per sale | whop.com |
| LaunchPass | Paid Discord communities with Stripe | Monthly plan + fees | launchpass.com |
| Ko-fi | Tips and memberships | About 5% + Stripe on memberships | ko-fi.com |
| Upgrade.Chat | Paid roles via webhooks | Fees vary | upgrade.chat |

Fees came from 2026 blog tables and disagree with each other; check each vendor's current pricing.
The bot's role must sit **above** the paid roles it gives out (LaunchPass's own docs say so).

### Music
| Bot | Good for | Cost | Website |
|---|---|---|---|
| Jockie Music | Most reliable surviving music bot; up to 4 instances per server | Free; premium | jockiemusic.com |
| FlaviBot | Cheap paid alternative | About $2/mo | flavibot.xyz |

✅ both, but music bots get shut down often (Groovy, Rythm, Hydra), so always re-check. Many YouTube-based players have stopped working.

### Stats & analytics
| Bot | Good for | Cost | Website |
|---|---|---|---|
| Statbot | Activity stats, top channels, member growth | Free; premium | statbot.net |

✅. Note that it stores message metadata, so mention privacy. The built-in **Server Insights** (Community servers) may be enough.

### Fun / economy (gaming and meme communities)
| Bot | Good for | Website |
|---|---|---|
| Dank Memer | Meme economy and minigames | dankmemer.lol |
| OwO / Mudae | Collecting, gacha and anime games (anime communities) | owobot.com / mudae.net |

⚠️ not checked in this pass. Keep fun bots to their own channel (for example `🎲┃bot-games`) so they don't flood chat.

## Picking by content profile

| Profile | Usually pick | Why |
|---|---|---|
| Gaming creator / streamer | Carl-bot, Arcane, Streamcord, GiveawayBot | Roles for platforms, XP keeps chatters coming back, go-live pings, giveaways for subs |
| YouTuber (any niche) | Carl-bot, a YouTube upload-alert bot, Apollo | Self-assign ping roles, new-video alerts, premiere/watch-party events |
| Selling products / courses / skills | Carl-bot or Dyno, Ticket Tool, Whop or LaunchPass | Customer role sync on purchase, private support tickets |
| Patreon creator | Patreon integration, Carl-bot | Tier roles sync automatically |
| Study group / course cohort | Apollo or Sesh, Carl-bot | Session scheduling across time zones, subject roles |
| Small business | Dyno, Ticket Tool | Moderation + private order/support tickets |
| Music producers | Carl-bot, Apollo, Jockie Music | Genre/DAW roles, listening-party events, music in voice |
| Crypto / finance | Wick, Carl-bot, Dyno | Anti-raid and anti-scam protection matter most here |
| Anime / fandom | Carl-bot, Mudae or OwO, Arcane | Spoiler/series roles, the games the audience expects |
| Big server (10k+) | Add Wick + Statbot | Raids and moderation load scale with size |

## Channels and roles bots need

Create these in the blueprint when you pick the bot, so the bot has somewhere to post:

| Bot job | Add to blueprint |
|---|---|
| Leveling | `level-ups` channel (read-only for members) |
| Stream/upload alerts | `live-now` or `new-videos` channel (read-only) + a `Live Ping` role (mentionable, `none` permissions) |
| Tickets | `open-a-ticket` channel (read-only; the bot posts its button there) + a private `TICKETS` category if the bot asks for one |
| Logs | `mod-log` inside the private staff category |
| Giveaways | `giveaways` channel (read-only) |
| Fun bots | `bot-games` channel with slowmode |

**Read-only channels and bots:** a bot without Administrator can't post in a read-only channel
unless its role is a writer. After the user invites the bot, Discord creates a role named after it
(for example `Arcane`). Add that name to the channel's `writers` and run `apply --update`.
