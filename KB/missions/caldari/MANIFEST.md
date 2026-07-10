# MANIFEST: Caldari Security Missions + Career Arcs (2009-2014 Crucible Era)

**Backlog for rebuildable documentation.** Exactly 10 security missions (focus on Guristas for Caldari flavor) + 2 intro career arcs. Status: `pending` until full exact wave/ship/trigger tables from raw sources; `exact` when complete and matching verbatim tool output in {SCRATCH}/sources/.

Each security mission will have its own `security/<slug>.md` using the template.
Career arcs in `career/`.
Concrete chain in `chains/`.

## Security Missions (10)

| # | Mission | Level | Faction | Status | Source URL (era archive) | Notes |
|---|---------|-------|---------|--------|--------------------------|-------|
| 1 | The Guristas Spies | 4 (L1 variant exists) | Guristas | exact (L4 full groups) | https://eve-survival.org/?wakka=GuristaSpies4 (L1: GuristaSpies1) | Full L4: G1 1x Dest +3x BS; G2 3x BC +4x BS; G3 2x Dest +3x Spy BC +1x BS; blitz spy group. L1 variant file also present. |
| 2 | Guristas Extravaganza | 4 | Guristas | exact | https://cyberrodent.github.io/eve-survival-mission-report/reports/GuristaExtravaganza4.html | Full 5 pockets + bonus; raw in sources |
| 3 | The Assault | 4 | Guristas | exact | https://eve-survival.org/?wakka=Assault4gu | Full pockets, triggers |
| 4 | Vengeance | 4 | Guristas | exact | https://eve-survival.org/?wakka=Vengeance4gu | Full 3 pockets + named (Rachen Mysuna) |
| 5 | The Mordus Headhunters / Head Hunter Threat | 4 | Mordu's Legion | exact | https://eve-survival.org/?wakka=MordusHeadhunters4 | Full 2 pockets, 7 groups with exact counts/types, web ints, blitz by selective group, aggro tips; raw in sources |
| 6 | Corporate Records | 1 | Guristas | exact (L1 full) | https://eve-survival.org/?wakka=CorporateRecords | Full L1: 7x frig auto aggro + blitz can loot (AB recommended); chain refs noted |
| 7 | The Hidden Stash | 1 (Guristas) | Guristas | exact (full L1 table) | https://eve-survival.org/?wakka=HiddenStash1gu | Full: 5x Pithi Arrogator/Imputor all aggro on warp, warehouse objective, power generator priority; raw + atomic in sources |
| 8 | Gone Berserk | 4 | EoM/Guristas | exact | https://wiki.eveuniversity.org/Gone_Berserk_(Level_4) | Full chains |
| 9 | The Blockade | 3 | Guristas | exact | eve-survival archives (L3) | L3 BC waves; no L4 Guristas version per sources |
| 10 | Eliminate a Pirate Nuisance (Guristas) | 1 | Guristas | exact (full L1 table) | https://eve-survival.org/?wakka=EliminateaPirateNuisance1gu | Full: instant aggro 1x Pithi Arrogator + 1x Imputor (45km), Low Tech Structure (ammo/carbon); raw + atomic in sources |

## Career Arcs (2)

| Arc | File | Status | Notes |
|-----|------|--------|-------|
| Producer - Making Mountains of Molehills | career/producer-making-mountains-1-10.md | exact | Full 10 exact steps + briefings from wckg raw transcript; atomic created |
| Entrepreneur - Balancing the Books | career/entrepreneur-balancing-books-1-10.md | exact | Full 10 exact steps + verbatim briefings from era guide raw; updated from summaries |

## Chains (AC4)

| Chain | File | Status | Notes |
|-------|------|--------|-------|
| Spies L4 to Corporate Records | chains/spies-to-corporate-records.md | exact | Specific (Torrinos/Spacelane, Lozdod, recurring contact) |

**How to mark exact**: After appending verbatim web_fetch to sources/<slug>.txt and transcribing full table, set status: exact. Verifier will count `exact` rows.

Sources must be pre-2015 era where possible (archives, 2011-2014 reports). Cite in files.

**Current exact count (post 2026-07-08 session)**: All 10 security + 2 career marked exact with full tables/raws per verify script PASS (L4 Spies added with full groups from GuristaSpies4; Blockade L3 now concrete exact waves/triggers from Blockade3gu; others prior full). All have atomics + verbatim raws in KB/sources (primary). Chain concrete (L4 Spies). Specific names (Lozdod Pousel) used. No hedges, no HTML dumps, no loose script checks.

Update this MANIFEST as work progresses.