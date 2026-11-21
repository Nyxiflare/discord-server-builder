# Community blueprints

Ready-made server layouts you can install as they are or adapt. Each one is a normal blueprint file
(see the "Blueprint reference" in [SKILL.md](../SKILL.md)).

| Blueprint | For |
|---|---|
| [indie-game-dev.json](indie-game-dev.json) | A game in development: devlogs, ideas forum, private playtests, bug-report forum |
| [podcast-community.json](podcast-community.json) | A weekly podcast: episode threads, listener questions, live recording stage, Patron area |
| [fitness-challenge.json](fitness-challenge.json) | Monthly fitness challenges: check-ins, form checks, goal roles, members-only progress photos |

The [templates](../assets/templates) (creator, gaming, digital products, study group, small
business, and a Spanish creator community) work as blueprints too.

## Use one

Ask Claude:

> Use the **podcast-community** blueprint for my server. My show is called "Late Night Lab".

Claude copies it, swaps in your names, voice and links, shows you the preview
(`preview blueprint.json`), and builds it after you approve. You can also run it yourself:

```bash
python scripts/discord_builder.py validate blueprints/podcast-community.json
python scripts/discord_builder.py preview  blueprints/podcast-community.json
python scripts/discord_builder.py apply    blueprints/podcast-community.json --guild YOUR_SERVER_ID --dry-run
```

Shared blueprints are untrusted input, and `validate` treats them that way:
- Roles can never be given Administrator; use the `admin` preset and give Administrator to your
  own role by hand.
- Emoji and sticker files must sit inside the blueprint's folder.
- Invite links, other links and @everyone/@here text in starter posts are listed for you to review.
- The bot never pings anyone, whatever the posts say.

## Share yours

1. Export your server (it strips every ID, member, message author and invite link):
   ```bash
   python scripts/discord_builder.py export --guild YOUR_SERVER_ID my-server.json
   ```
2. Read it through: remove anything private from topics and starter posts, and replace your
   brand names with something generic if you want others to reuse it.
3. Add a one-line `"_about"` at the top saying who it's for, then run `validate` (no errors) and
   `health` (aim for 80+).
4. Open a pull request adding it to this folder and a row to the table above.
