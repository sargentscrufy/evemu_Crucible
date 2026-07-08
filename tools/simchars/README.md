# simchars — sim-character framework (Phase 3 foundation)

Provision and operate NPC "player characters": real protocol clients with
characters, skills, ships, and fits chosen per archetype. Built on the
smoke-bot codec; all packet shapes verified against live client captures.

## What works today (verified live)

The full provisioning pipeline, run against a real server with the Aura
Vasanen character:

```
fund wallet (DB, offline)
-> grant archetype skills (DB, offline; recursive prerequisite closure)
-> recover stranded ship to dock perimeter if a prior run left it in space
-> login, enter world, dock if needed (CmdStop + CmdDock w/ retries)
-> buy ship + modules from the local market (PlaceCharOrder immediate)
-> AssembleShip -> ActivateShip -> fit modules to slots -> verify
-> optional undock/redock round trip
```

```
python provision.py --user aura --password aura --char-id 90000002 \
    --archetype hauler --home-station 60004450 [--undock-test]
```

## Layout

- `machoclient.py` — protocol session: service calls, object binding,
  bound-object calls, session tracking. The bot framework's spine.
- `db.py` — Director-side DB access: funding, skill grants, item/market
  queries, stranded-ship recovery. Tier-1 actors legitimately own the DB
  (plan.md); anything with a working client path uses the protocol instead.
- `fits.py` — archetype fit templates by type NAME (data-drift safe),
  validated at provision time against the hull's real slot layout.
- `provision.py` — the pipeline above.

## Hard-won protocol facts (cost a day of live debugging — keep!)

1. **Typed dispatch**: the server matches handlers by argument type.
   Chat text must be PyWString; prices must be PyFloat. Wrong type =
   "Unable to find method to handle call" and a silently dropped call.
2. **AssembleShip must get a LIST** — the single-int overload re-checks
   the original tuple and silently no-ops (bug SHIP-1 in doc/bug-log.md).
3. **Fit only the ACTIVE ship** — InventoryBound::MoveItems resolves
   module slots against `client->GetShip()`, not the bound inventory.
   Order: ActivateShip, then Add(module, station, flag=slot).
4. **Board is for space; ActivateShip is for docked** ship switching.
5. **CmdStop before CmdDock after login-in-space** — login warp-in can
   wedge destiny in a broken align state that silently eats dock requests.
6. **Server caches are authoritative while online**: DB writes to wallets
   or skills are invisible until the character is fully unloaded
   (and abrupt disconnects can leave stale ItemFactory entries — a server
   restart clears them; a graceful logout usually suffices).
7. Character creation needs the full doll (empty dicts segfault: CHAR-1);
   portraits are plain JPEGs at `image_cache/Character/<charID>_512.jpg`
   (or photoUploadSvc.Upload *before* CreateCharacterWithDoll).

## Archetypes and the Director (design)

Each sim character = account + character + archetype. The archetype
selects: fit templates (this package), behavior loop (future), chat
persona (ollama model/system prompt — see aura_bot.py), and funding policy.

- **hauler** — works today. Next: cargo pickup/delivery loop between the
  seed-v2 hub buy-walls and fringe markets (doc/design/market-economy.md).
- **miner** — needs belt warp (blocked on DESTINY-3 warp rework).
- **responder** ("CONCORD as players") — design:
  - The Director (external service) watches for hisec violations. Sources,
    best-first: (a) admin API events once Phase 2 lands, (b) polling
    chrKillTable / wallet bounty journal, (c) log tail.
  - On violation: wake N dormant responder characters (pre-provisioned
    in nearby stations by this pipeline), undock, warp to the violator's
    grid (needs DESTINY-3), engage or tackle, then return and dock.
    They are real characters: visible in local, killable, chatty.
  - Response strength scales with system security, mirroring CONCORD.
  - Until warp works, responders can only posture in local ("CONCORD is
    aware of your activities") — which is already atmospheric.

## Local models as decision engines (user direction, 2026-07-08)

aura_bot.py proved perception -> ollama -> action for chat. The same
pattern generalizes: give the model a compact world-state summary
(assets, location, market spreads, standing orders) and a constrained
action vocabulary (haul/route/buy/sell/dock/flee), let the script parse
the chosen action, and keep hard game mechanics in deterministic code.
Good first target: the hauler's route/cargo selection — low stakes,
easy to validate against the market data it acted on.
