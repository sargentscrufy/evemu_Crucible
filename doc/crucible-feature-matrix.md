# Crucible Feature Matrix

**Status:** Phase 0 draft — tier assignments reflect intent; the "verified" column gets filled in by Phase 1 smoke tests, not by reading code.
**Pinned client:** EVE Online **Crucible v1.6.5, build 360229** (`EVEVersionNumber 7.31`, `MachoNetVersion 320` — see `src/eve-common/EVEVersion.h`). We never chase newer client builds or protocol versions.
**Scope:** Private, single-tenant server. Population is one-to-a-few humans plus AI-simulated characters.

## How to read this

- **Tier 1 — Core loop (must be rock solid):** a crash or major defect here is a stop-ship bug. These paths are exercised by the CI smoke bot.
- **Tier 2 — Supported (should work):** defects are fixed as prioritized backlog. Bot soak tests exercise these over time.
- **Tier 3 — Best effort (works as-is):** we accept upstream behavior; fixes only if cheap or blocking a Tier 1/2 feature.
- **Out of scope:** explicitly not maintained; may be disabled outright.

## Tier 1 — Core loop

| Feature | Server area | Verified |
|---|---|---|
| Login / account auto-creation / character creation | `Client`, `ClientSession`, `character/` | ☐ |
| Docking, undocking, station services | `station/`, `system/` | ☐ |
| Warp, jump gates, autopilot, movement (destiny) | `system/DestinyManager` | ☐ |
| Targeting, weapons, basic PvE combat | `ship/`, `dogmaim/`, `npc/NPCAI` | ☐ |
| NPC spawns (static, roaming, respawn) | `system/cosmicMgrs/SpawnMgr` | ☐ |
| Market (orders, transactions, wallet) | `market/` | ☐ |
| Mining, asteroid belts | `system/cosmicMgrs/BeltMgr` | ☐ |
| Ship fitting, modules, capacitor | `ship/modules/`, `dogmaim/` | ☐ |
| Skills and training | `character/` | ☐ |
| Inventory, cargo, item movement | `inventory/` | ☐ |
| Chat (local, channels) and mail | `chat/`, `mail/` | ☐ |
| Persistence: clean save/restore across restart and crash | `ServiceDB`, `DBCleaner` | ☐ |

## Tier 2 — Supported

| Feature | Server area | Verified |
|---|---|---|
| Agents and missions (courier, kill) | `agents/`, `missions/` | ☐ |
| Manufacturing, research (S&I) | `manufacturing/` | ☐ |
| Drones and drone AI | `npc/Drone*` | ☐ |
| Corporations (join, offices, hangars, wallet) | `corporation/` | ☐ |
| Standings, factions, CONCORD/security response | `standing/`, `faction/`, `npc/Concord` | ☐ |
| Exploration, anomalies, scanning | `exploration/`, `cosmicMgrs/AnomalyMgr` | ☐ |
| Dungeons / deadspace | `dungeon/`, `cosmicMgrs/DungeonMgr` | ☐ |
| Fleets | `fleet/` | ☐ |
| Insurance, cloning, medical | `character/`, `station/` | ☐ |
| Reprocessing / refining | `station/` | ☐ |
| Search | `search/` | ☐ |
| PvP combat (player vs player, incl. bot "players") | `ship/`, `system/` | ☐ |

## Tier 3 — Best effort

| Feature | Server area | Notes |
|---|---|---|
| POS (starbases, towers) | `pos/` | Historically incomplete upstream |
| Planetary Interaction | `planet/` | Historically incomplete upstream |
| Contracts | `contract/` | Partial upstream |
| Alliances | `alliance/` | Low value at private-server population |
| Wormholes | `cosmicMgrs/WormholeMgr` | Crucible-era WH space; verify before promising |
| Sovereignty / nullsec infrastructure | `system/` | Meaningless without large population |
| Kill mails / combat logs | `ship/` | Nice to have |
| Old EVE XML API / image server | `apiserver/`, `imageserver/` | Reference implementations; superseded by planned admin API |

## Out of scope

- Anything post-Crucible (Inferno+ features, newer ships/modules/regions).
- Public-server concerns: horizontal scaling, anti-cheat, account security beyond basic auth, GDPR-ish data handling.
- Client modifications or patching beyond what's needed to point it at the server.
- Multi-server / cluster deployments (single docker-compose stack only).
- Localization (English client assumed).

## Standing decisions

1. **Client build 360229 is immutable.** Any change that breaks compatibility with it is a regression, full stop.
2. **Tier assignment changes are plan changes.** Promoting/demoting a feature happens in this file via PR, not ad hoc.
3. **The smoke bot defines "verified."** A ☐ becomes ☑ when a scripted bot (or documented manual script) exercises the path end-to-end against a fresh docker stack.
