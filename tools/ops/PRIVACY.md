# Privacy — local ops only

This directory is for **host-side** Docker/EVEmu operations on a private
dev machine. It is not a shipping surface.

## Never commit

| Path | Why |
|---|---|
| `backup/` | SQL dumps / volume tarballs can contain **account password fields and hashes**, character rows, wallets |
| `logs/` | Runtime recovery logs |

Both are listed in the repo root `.gitignore`.

## Do not put in docs or scripts

- Personal **account names** used for playtest logins  
- Personal **passwords** or password hashes  
- Paste of `account` table rows  

Use generic bot accounts in committed scripts (`aura` / `fleet` / `smokebot`) only.

## Local DB is not “the project”

Character and account data live in the Docker **volume** (`evemu_db`), not in
git. Resetting a password updates the database only.

## Pre-existing lore / research under `KB/` and `doc/`

Files that discuss a public EVE Online character identity (corp history,
killmails, etc.) are separate from login credentials. If those should also
leave the tree, say so and they can be removed or moved out of the repo
explicitly — they are not passwords, but they do name a character.
