# Security (Encounter) Missions — Implementation Plan

**Status: PLANNED — highest-impact TODO from the Crucible project-status matrix**

## Why this is the pick

The official EVEmu Crucible status matrix (wiki.evemu.dev, Oct 2024) rates
Security Missions **0% — NOT IMPLEMENTED**, and our fork inherits that: the
server boots with `MissionDataMgr: 38(15) courier sets, 0 mining, 0 ENCOUNTER`.
Security missions are the bread-and-butter PvE loop of EVE — the single thing
a new pilot does most in the first hundred hours. Every prerequisite is now in
place *on our fork specifically*, which was not true upstream:

| Prerequisite | State on our fork |
|---|---|
| Agents offer/accept/complete flow | ~80% (official), courier E2E validated by our bots (MISSION-4/5/6 caveats known) |
| Mission rewards (ISK/LP/standings) | Working (95% official) + our STAND-1/2/3 standing writes |
| Combat pipeline | Fully validated both directions (damage, locks, ammo, kill, wreck, loot, pod) |
| NPC spawning/AI | Working + hardened (SPAWN series, NPC-1/2/3, aggro fixes, EWAR) |
| Dungeon manager | Mission Dungeon Creation/Destruction ~95% per official matrix |
| Kill detection hook | `NPC::Killed` — we already extended it once (STAND-1 faction loss) |
| Bot QA harness | mission_qa.py (courier), combat bots, standings bots — extendable |
| Mission content research | `KB/` — the user's Crucible mission research (Caldari security arcs) |

It also directly serves this server's vision: AI "player" mission-runners need
the same content, and friends on production get the core gameplay loop.

## Scope

L1 and L2 security missions from empire agents, two structural types:

1. **Open-space encounters** — warp to a mission location in normal space,
   kill the spawned group, return to agent. (M1–M2)
2. **Deadspace pockets** — acceleration-gate-linked rooms with staged waves.
   (M3+)

Out of scope for v1: storyline/arc/anomic/COSMOS chains, ship restrictions,
mission-specific triggers/scripting beyond kill-all and kill-named.

## Architecture (file:line anchors)

- **Content**: `MissionDataMgr` loads mission sets from DB tables
  (`agtMissions*` family). ENCOUNTER rows are absent — this is a *content*
  gap first, code second. Courier rows are the template to mirror.
- **Offer/brief**: `Agent::MakeOffer` / mission briefing path already carries
  objectives + rewards for courier; encounter briefs need objective text +
  location (system/dungeon ref) instead of pickup/dropoff.
- **Spawn**: `DungeonMgr` (anomaly + mission dungeon creation "95%") +
  `SpawnMgr` for the kill group. Mission dungeons anchor at a deadspace
  point in the agent's constellation; v1 spawns the group directly at a
  mission bookmark point (no gates).
- **Objective tracking**: new `MissionObjectiveMgr` (or fields on the active
  mission record): counts kills of mission-tagged NPCs. Hook:
  `NPC::Killed` (same place as STAND-1) — if the NPC carries a missionID
  tag and the killer (or their fleet) owns that mission, decrement the
  remaining-kills counter; at zero, flag objective complete and notify
  (`OnMissionObjectiveUpdated` / agent talk-to-complete like courier).
- **Completion/rewards**: existing courier completion path (validated) —
  ISK + LP + standing delta via `Agent::UpdateStandings` (works).
- **MISSION-4/5/6 fixes ride along**: GetMissionObjectiveInfo returning
  None, active-mission-blocks-new-briefing (no Quit button path), and
  server-side mission cache needing restart — all three touch the same
  agent/mission state code this work opens up.

## The retail flow — user spec from live playtesting (2026-07-13)

This is the target experience, written by the user after running the M1
slice, and it defines M2/M3:

1. **Clear briefing fiction**: "these logs were on a freighter that was
   ambushed and boarded by X-faction pirates; go in and retrieve them."
   (Custom prose per mission — string mission titles are proven to render,
   so string briefings are the same mechanism: send briefing text as a
   string for custom missions. Add a `briefing` TEXT column to qstKill.)
2. **Journal / right-click location**: mission site appears under its own
   right-click-space submenu (retail called it Encounters), not Personal
   Locations — driven by agent mission bookmarks on the offer
   (offer.bookmarks; client routes warps through agentMgr WarpToLocation,
   already implemented). Personal-Locations drops stay as debug fallback.
3. **Warp-in is safe**: no hostiles at the warp-in point — just an
   **acceleration gate**. Activate → ship aligns → warps to the pocket.
4. **Pocket theater**: on player arrival the enemy leader **broadcasts in
   Local** ("I've killed the crew and taken the reports... too bad you
   won't live to take them back") — LSC hooks from the feedback system
   can post to system local as an NPC speaker.
5. **The fight**: 2–4 frigate henchmen aggro immediately (NPC AI already
   does sight-range aggro) plus a hostile **transport**.
6. **The drop**: killing the transport drops a wreck/container holding the
   objective item (NPC::Killed hook + mission-tag registry: tagged NPC's
   wreck gets the goal item injected). L1 difficulty: easy.

## Status — 2026-07-14

Implemented and awaiting a live playtest (not yet built or bot-tested):

- **Briefings are real prose, served from the DB.** `qstKill` gained
  `briefing` + `leaderLine` TEXT columns; `GetCustomBriefing()` reads them
  instead of a hardcoded C++ switch, so mission text can be rewritten
  without a server rebuild. Prose names the faction (Guristas), the
  ambushed freighter, and the objective, per spec item 1.
- **Mission location shows up.** `BuildEncounterBookmarks()` fills
  `offer.bookmarks` (was always an empty `PyList` — the root cause of "we
  still don't get a mission location") with the combat site
  (`objective.source`) and the agent station (`objective.destination`).
- **The site is shaped like retail** (spec items 5 + 6): leader
  (Pithi Wrecker) + 2–4 Pithi frigate henchmen + a **Guristas Hauler that
  is carrying the objective**. The free-floating "Mission Objective
  Container" is gone.
- **The transport drops the goods.** `RegisterMissionDrop()` tags the
  hauler's itemID at spawn; `NPC::Killed` calls `InjectMissionLoot()`,
  which spawns the goal item straight into the hauler's wreck.
  Deliberately NOT gated on `LootDropChance` — a failed roll would make
  the mission silently uncompletable.

**DEPLOY NOTE — this will break if you skip it:** `LoadKillData` now
selects `q.briefing, q.leaderLine`. Against an *old* `qstKill` that query
errors, no encounter sets load, and `CreateMissionOffer` silently falls
back to courier missions. `sql/seed_and_clean/seed_missions_kill.sql` must
be re-applied (it drops + recreates the table) before running the server.

### Not done yet

- **Acceleration gate + pocket (spec items 3 + 4).** The site is still a
  single deadspace point in open space, warped to directly. There is no
  gate and no second pocket. This is the biggest remaining gap.
- **Local broadcast (spec item 4).** `LSCChannel::SendMessage()` is
  attributed to a `Client*`; there is no server-side path to speak as an
  NPC without hand-rolling an `OnLSC` notification with a spoofed sender.
  The leader's `leaderLine` currently arrives as a client notification on
  warp *start*, not as Local chat on arrival. Both need fixing together.
- **Restart durability.** `m_sitePoints` and `offer.bookmarks` are
  in-memory only. A server restart mid-mission loses the warp point and
  the journal bookmarks (the offer itself survives in `agtOffers`).

## Milestones

### M1 — Content + spawn primitive (open space)
- Author 5 handcrafted L1 Caldari security missions from `KB/` research
  (name, brief text, target group composition, reward numbers tuned to
  Crucible-era L1: ~100–300k ISK + time bonus).
- DB: ENCOUNTER mission rows + a `missionSpawnGroups` table (missionID →
  npcTypes/counts/point).
- On accept: create mission bookmark (system anchor point ~ deadspace-safe
  coordinates), spawn the group tagged with missionID via SpawnMgr.
- Despawn on quit/expiry; respawn-on-warp-in guarded (lessons from
  SPAWN-9/10/11/14).
- **Exit test**: bot accepts, warps to bookmark, group is there, correctly
  composed, no spawn-manager interference.

### M2 — Objective tracking + completion loop
- missionID tagging on spawned NPCs; `NPC::Killed` hook decrements.
- Kill-all objective completion → agent completion → ISK/LP/standings paid
  (verify standings via STAND-1 read path).
- Fix MISSION-5 (offer/accept state machine allows quit/decline properly)
  and MISSION-6 (mission state cache invalidation without restart) while
  in this code.
- **Exit test**: combat bot (civilian-gun Cormorant or smartbomb Merlin —
  the validated kill loadouts) runs the full loop: accept → warp → clear →
  return → paid. Repeat 10x across the 5 missions; wallet/standing deltas
  conserved.

### M3 — Deadspace pockets + acceleration gates
- Acceleration gate entity (typeID exists in Crucible data): activate →
  server-controlled warp to next room point (reuse WarpTo with fixed
  destination — our destiny rework makes this safe).
- Gate gating: room N+1 locked until room N objective met (simple flag on
  the mission dungeon record).
- 2-room variants of two existing missions.
- **Exit test**: bot uses the gate (new `activate_gate` protocol helper),
  clears both rooms, completes.

### M4 — L2 tier + variation + polish
- L2 missions (bigger waves, cruiser-class rats), wave escalation on aggro
  (SpawnMgr wave support exists from belt work).
- Procedural variation: pick group composition from faction tables
  (GetRegionRatFaction) so repeats aren't identical.
- Loot/bounty tuning; mission flagging of wrecks (loot rights v1: free).
- Balance pass against NPC-4 feedback (rat strength vs sec status).

### M5 — Soak + release
- 3 bot mission-runners cycling L1/L2 missions for 24h alongside the
  trader/hauler fleet; watch for spawn leaks, dungeon cleanup, memory.
- Agent-access standing gate (the deferred STANDINGS item) if time allows.
- Stage to production (rev N) with mission content in the release notes.

## Risks / known traps
- **Mission state caching** (MISSION-6): the server caches agent/mission
  state aggressively; plan the invalidation story first, not last.
- **Spawn bookkeeping**: every belt-spawn bug (SPAWN-9..14) came from
  ad-hoc spawn ownership. Mission spawns must be owned by the mission
  record, not the belt/roam machinery.
- **Dungeon anchoring**: mission dungeons must not collide with anomaly
  dungeons or belts (bubble allocation — GRID lessons apply).
- **Client expectations**: the Crucible client renders mission objectives
  from specific packet shapes — capture a real courier accept/complete via
  the proxy first and mirror the encounter shapes against it.
