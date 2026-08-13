*** Private Server Fork - upstream triage ports (2026-08-12) ***
Cherry-picks / adapts from EvEmu-Project staging + open PRs; keep fork separate.
- [FIX] NETWORK-3: ProcessNet per-packet SafeDelete leak; EVESession never nulls handler (upstream #311)
- [FEAT] FIT-1: CharFittingMgr save/load + shipFittings migration (upstream #317; no escape-on-read)
- [FIX] DESTINY-14: no 0.5 AU login offset; skip login warp when near saved pos; WarpOut SaveShip (adapt #323 e81d449)

*** Private Server Fork — playtest polish (2026-08-02 / 03) ***
Live interactive playtest (SARGENTSCRUFY / Cold Steel 2) + stability polish.
- [FIX] TURN-1: gate approach turn/snap — live target heading each tic, unit nlerp, no PositionHack on ClearTurn, publish CmdGotoDirection while turning
- [FIX] JUMP-CLOAK-1/2: gate jump session cloak FX (30s duration OnSpecialFX14); uncloak never sends duration 0 (client TypeError)
- [FIX] LOGIN-CLOAK-1: login-from-space stuck cloak — re-enable LoginCloak timer (20s), force UnCloak on login warp complete
- [FIX] WARP-LAND soft residual facing travel; GRID-WARP-1 no RemoveBalls mid-warp (belt doesn't vanish)
- [FIX] GUN-FX-1/2: Godma duration ms; FX before damage so kill-shots don't kill the client fxSequencer
- [FIX] HOSTILE-1: combat NPCs securityStatus -10 (no "peaceful entity" confirm on rats)
- [FIX] DRONE-4/5/6: Warden idle/halt, SetOwner on launch, bandwidth load reset, engage/return ownership helper
- [FIX] CAP-2 capacitor HUD regen list; CAP-1 undock full tank
- [QoL] Login Local MOTD + modal patch notes (working / known soft / BUG reporting)
- [OPS] No mid-session redeploy while pilots in space (redeploys look like "crashes" — exit 143 SIGTERM)
- Open: warp align timeout force-InitWarp (log noise), Neocom skill float TypeError on login, intentional destroyable belt rocks

*** Private Server Fork — phase-1-commerce checkpoint (2026-07-15) ***
Full human-readable report: [PROGRESS.md](PROGRESS.md).  Highlights since the last entry:
- [FEAT] Security (encounter) missions, absent upstream, now run the full retail arc: DB-driven Guristas mission content (7 missions, L1/L2), acceleration gate -> deadspace pocket, scenery, leader taunts, escorts that fight back, objective container drops, journal bookmarks, working agent-menu Warp (reverse-engineered from client localization + call-signature data). Bot-certified 9/9 end to end
- [FEAT] Bot economy: arbitrage traders with personalities, NPC-corp market replenishment, escorted convoys, multi-system routing; market matching rebuilt (range-aware, partial fills, order crossing) and bot-certified 15/15
- [FEAT] Industry validated end-to-end (reprocess/manufacture/ME/TE research/copies/PI CC); smartbombs implemented; standings loss + faction police response
- [FIX] NPC-FIRE-1: any NPC the player shot first never started its weapon timers -- every reactively-aggroed rat on the server had been permanently silent
- [FIX] The stuck-warping family closed out (DESTINY-12 watchdog, DESTINY-13 in-warp mode demotion) plus TARG-1/TARG-2 lifetime crashes, WEAPON-1/2, CAP-1 (empty capacitor sessions), PROP-1 (client crash targeting scenery), CAN-SLIM-1 (jetcan slims poisoned grid updates), EFFECT-2 (weapon fx rebuilt to live's per-cycle one-shot stream), NETWORK-2 (disconnect destructor-order UAF)
- [QoL] Login MOTD dialog, full cap+shield on undock, undock throttle (100% full burn accepted / preferred in live play), warp-in standoffs, boot-time purge of leaked mission objects

*** Private Server Fork — phase-0-foundation (2026-07-08) ***
- [FEAT] Drone control (DRONE-1/2/3): engage/return-home/return-to-bay wired to DroneAIMgr with ownership checks; return-to-bay auto-scoops on arrival (deferred outside the entity tic loop); off-grid drone state changes now reach the owner (no more "Drones in Distant Space" ghosts). Live-verified: launch, engage, recall, scoop
- [FEAT] In-game dev feedback log (FEEDBACK-1): local chat is appended to server_cache/feedback.log with char/system/ship context lines on login and jumps; event-driven with 5MB rotation. Players narrate bugs in Local; admin pulls the file for analysis. Validated live via bot chat
- [FEAT] Empire police gate patrols (GUARD-1): gates in >0.90 sec systems spawn faction police 10-30s after a pilot arrives; guards idle-orbit the gate at 15km, retaliate but never initiate, resume patrol after fights. First step toward simulated CONCORD response. Bot-validated live (3 Caldari Police Lieutenants patrolling the Amsen->Ekura gate)
- [FIX] Deferred undock push stomped active warps (DESTINY-5): warping right after undock re-aimed the warp at the undock vector x1e16 and flung ships tens of thousands of AU into deep space; found and verified fixed by bot validation flights
- [FEAT] 8000km grids (GRID-2): spatial partitions grown 26x (CCP's own 2016 TQ solution, server-side only) -- grid-wipe seams (PHYS-2) become practically unencounterable; belt hysteresis kept as backstop
- [FIX] Warp use-after-free (GRID-3): the warp target-bubble pointer was held across align+warp while the bubble reaper deleted empty grids every 60s -- server segfault mid-warp (likely the historical DESTINY-1 crash); target grid now re-resolved every warp tick
- [FIX] Rats rendered motionless in combat (NPC-1): the one-time SetBallSpeed broadcast for NPCs was suppressed by a spawn-time flag, so clients simulated them at 0 m/s while taking real damage
- [FIX] NPCs sent a bare 3-key slim (NPC-2): clients now get category/group/owner/security so rats classify as combat NPCs (turret fx, overview, combat cues)
- [FIX] NPC client-position drift (NPC-3): server npc movement is not tick-identical to the client sim; moving npcs/drones now broadcast an authoritative position snap every ~10s
- [FIX] Gate police multiplied forever (GUARD-1 runaway): belt chain-respawn logic cleared the gate bubble's spawned flag every minute; highsec gates now spawn one patrol, verified by bot flight
- [FIX] Weapon/mining beams never rendered (EFFECT-1): ship slim sent the fitted-module list in reversed pair order, silently breaking client turret mounting; both slim builders now use the packet-capture-verified order
- [FIX] Mined ore was invisible (CHAR-4): ore routed to the ore hold (flag 134) which the Crucible client predates; ore now goes to cargo
- [FIX] Module onlining never checked skills (SKILL-1); docked onlining skipped every check
- [FIX] Belt spawn timers could permanently disable themselves (SPAWN-9); bubbles re-arm while players are present
- [FIX] Gate bubbles registered gate itemID 1 (GATE-1: SetGate called with a bool)
- [FIX] NPC rat spawn rework (SPAWN-1..8): roaming spawns actually roam (timer wired, warp between belts, never yanked from watched grids), stamp comparisons and overflow fixes, spawn-kill iterator guards
- [FEAT] Warp physics rework (DESTINY-3): CCP warp curve scaled by ship warp speed; continuous velocity through accel/cruise/decel; no more landing overshoot or 10km target shove. Verified live by bot regression (undock -> 2.75AU warp -> return warp -> dock; ~40m landing error)
- [FEAT] Market Seed v2: hub-weighted market bootstrap — one trade hub per region with full catalog and NPC buy walls (minerals/ore/salvage/PI), thinner fringe stock with hub/fringe price gradients that make hauling profitable; staggered order lifetimes; 14-day price history backfill; re-seedable without touching player orders
- [FEAT] simchars framework: provision NPC "player characters" end-to-end — archetype fit templates validated against hull slot layouts and the local market, skill grants with prerequisite closure, protocol market purchases, ship assembly/fitting/activation, dock/undock automation, stranded-ship recovery, live warp regression test
- [FEAT] Headless protocol tooling: login smoke bot (nightly CI gate), verified Python marshal codec, transparent debug proxy on the client port with decoded traffic logs and raw byte capture
- [FEAT] Aura Vasanen PoC: ollama-driven NPC player character — protocol character creation, station presence, converses in Local via a local LLM
- [FEAT] Sim-character portraits served from the image cache
- [FIX] XMLParser::ElementParser missing virtual destructor (undefined behavior, caught by the new ASan CI job on its first run)
- CI: AddressSanitizer/UBSan build job, phase-* branch triggers, nightly dockerized login smoke test
- Docker: container healthchecks and restart policies (crash auto-recovery), game port remapped behind the capture proxy, Seed v2 wired into first-boot init (Lonetrek added to default regions)
- Docs: private-server redirection plan, Crucible feature matrix (pinned client 360229), admin API seam design, market economy design, live-testing bug log (open: DESTINY-4 align wedge, CHAR-1 doll validation segfault, SHIP-1 AssembleShip int overload)
- KB: Crucible-era mission research (Caldari security arcs, career missions) toward future mission fidelity

*** 0.8.6 ***
- [FEAT] MarketBot
- Market system fixes
- Contract/corp system fixes
- Various space manoeuvring fixes
- CI/CD system improvements and fixing build issues with Docker
- Many minor bugfixes and stability improvements

*** 0.8.5 ***
- [FEAT] Dungeon Editor
- [FEAT] Cynosural Field Generators
- [FEAT] Jump Drives
- [FEAT] Outpost creation and destruction
- [FEAT] Wormholes
- [FEAT] Loyalty Points, mission rewards and store
- Support aarch64 architecture
- Complete service rewrite
- Many minor bugfixes and overall improvements

*** 0.8.4 ***
- Added support for aarch64 with docker-compose
- [FEAT] Alliances Implemented
- [FEAT] Sovereignty Implemented
- Fixed bug in PI database causing segmentation fault
- Fixed sales tax default to 1%
- CustomError system reimplemented
- Updated ImageServer to allow for Alliance logos to be uploaded correctly
- Replaced liveupdates with updated versions
- Implemented new Database management tool (EVEDBTool) for migration versioning
- Implemented automatic market database seeding

*** 0.8.3 ***
- Fleet Implemented

*** 0.8.2 ***
- [FEAT] PI Implemented
- [FEAT] Basic POS Implemented

*** 0.8.1 ***
- [FEAT] Agents and Courier Missions Implemented

*** 0.8.0 (26/03/2021) ***
This release brings in massive new core system updates to EVEmu. These changes will dramatically increase the rate of change to this repository and make future contributions easier.

- Returned to numbered versioning
- Large new update to all core systems from Alasiya EvE (all credits to Allan for his fantastic work here)
- Database has been updated to reflect core changes to the server code
- Repository has been organized for quality of life
- CI configuration has been added for automated building of EVEmu binaries to be distributed
- Docker Compose support has been added to make the setting up of a new server quick and easy

*** 22/07/2008 ***
- Added autotools

*** 03/05/2008 ***
- Eliminate invBlueprints table by pulling data from other existing tables. (Bloody.Rabbit)
- Implemented bubble manager to handle in-space items which are not visible system wide.
- Partial support for boarding an empty ship in space.
- Properly undock to the station's dock location (firefoxpdm)
- Properly use ships position in space from the DB.
- Store ship position in space when logging out.
- Improved support for fitting charges with weapons.
- Improved NPC AI to make them consistently follow, orbit and attack.
- Hybrid and Laser modules consistently fire on NPCs now.
- Implemented damage code including basic messages.
- Implemented NPC death logic.
- Implement code to support asteroids in space.
- Add new command to spawn an asteroid: /roid (typeID) (radius)
- Implemented graphics for mining lasers (they do not yet actually mine though)
- Load up space junk (roids, items, etc) from DB ay system boot.
- Implement runtime memory error exception handler to help prevent one bad action from crashing the whole server.

*** 02/15/2008 ***
- Load tutorial information from DB (Bloody.Rabbit)

*** 02/03/2008 ***
- Celestial Statistics support (firefoxpdm)

*** 11/24/2007 ***
- Reworked bind ID storage code (firefoxpdm)
- More coporation cleanup (firefoxpdm)
- Fix issue with the wallet (firefoxpdm)
- Fixed "show info" tab for DoGetStation (firefoxpdm)
- Fixed station backgrounds (firefoxpdm)
- Implemented people and places lookup (firefoxpdm)
- Fix for owner notes (GuristaSyndicate)
alter table chrOwnerNote CHANGE content note TEXT NOT NULL;

*** Release 229 ***

*** 10/20/2007 ***
- Intial market implementation:
  - Major work on special market packet encodings.
  - Browse market, see pending orders.
  - Initial price history implementation.
  - Place sell orders (builds the market)
  - Place buy orders
  - Place immediate sell orders
  - Place immediate buy orders
  - you prolly need to log out&in before seeing new orders right now.
- Major destiny (space) work:
  - Much improved event broadcasting to allow players to
    observe the actions of another player.
  - New module manager to handle different weapon types
  - Improved timer support for module activation/deactivation.
  - Can now activate weapons and generate fake hits on targets.
  - Initial infrastructure for damage propigation.
- A bit more corporation creation work. (firefoxpdm)
- Initial NPC AI work. Very very simple right now.
- Added /spawn (typeID) command to spawn an NPC.
- Started reworking chat channels a bit. It is prolly more broken
  than it was previously right now, but should improve over time.
- Start rework on chat channels to support dynamic channels.
- Initial XML packet support for none-value duality handling.
- Added queue for destiny updates to properly batch them up.
Update SQL:
ALTER TABLE market_orders DROP `isBuy`;
ALTER TABLE market_orders CHANGE `bid` `bid` tinyint(3) unsigned NOT NULL default '0';
ALTER TABLE market_orders CHANGE `issued` `issued` bigint(20) unsigned NOT NULL default '0';
ALTER TABLE market_orders CHANGE `issued` `issued` bigint(20) unsigned NOT NULL default '0';
ALTER TABLE market_transactions CHANGE `transactionDateTime` `transactionDateTime` bigint(20) unsigned NOT NULL default '0';
ALTER TABLE market_transactions ADD `regionID` int(10) unsigned NOT NULL default '0';
New Table: billsPayable
New Table: market_history_old

*** 07/25/2007 ***
- Major revelation with destiny updates, fixes 'jumpy' movement in space.
- Much better understanding of the binary destiny update structure.
- Significant work on the destiny manager. Server now tracks client movement for
  warp, goto direction, and follow movement modes (orbit is the only major mode pending).
- Some initial drone launching code (not working yet)
- A bunch of makefile cleanup.
- Added support for the <files><cache>.. element in config file to cache the cache files
- Implemented a keepalive ping to hold idle sessions open.
- Added support for server originated messsages: error, infomodal, and notify
- Made persistent attributes auto-store.
- Fix for crash when jumping between systems.
- Owner Note implemented. (firefoxpdm)
- Corp channel creation and logo fixes (firefoxpdm)
- A bunch of other corporation creation stuff (firefoxpdm)

*** 5/01/2007 - 182 ***
- Initial targeting system
- Some support for training new skills from a skill book. It may work some times.
- added new command /search which searches items for summoning purposes
- added functionality to support the server sending you evemails (like for long search results)
- Initial standing history support (firefoxpdm)
- Initial corp creation code (firefoxpdm)
- Reworked the database priming technique.
- Merged the agtAgents2 table into agtAgents
- A few fixes for static owner querying.
- Initial ability to equip and activate modules (may not persist properly)

SQL Changes:
new table: chrStandingChanges
ALTER TABLE `corporation` CHANGE `corporationID` `corporationID` INT( 10 ) UNSIGNED NOT NULL AUTO_INCREMENT;
ALTER TABLE `corporation`  AUTO_INCREMENT =2000001;

*** 4/22/2007 - 169 ***
Major increase in error checking of generated xmlp objects
New FastEncode() operation on generated xmlp objects to reduce copying
A new mode of element operations in xmlp (non-pointer)
Major reworking of all item stuff to use the new inventory system


alter table entity AUTO_INCREMENT=140000000;
alter table dgmAttributeTypes CHANGE attributeID attributeID INTEGER UNSIGNED;
new table entity_attributes

*** 04/15/2007 ***
- Implemented initial employment history support (firefoxpdm)
- Implemented Character Note (LSMoura)
- Got evetool building on win32, still needs some work though.
- Added `unmarsahal` command to evetool to decode strings from logserver.
- Dramatic reworking of service calling mechanism to support names args and exceptions.
- A few fixes pointed out by sgi's audit tool.
- Got the market to display items, and active orders (cannot place or view orders though).
- More work on agents, still no significant progress
- Initial rev of EVEMail (FireFoX)
- Char creation information loading based on selected values (FireFoX)
- An initial implementation of /tr for some GM menus.

- Implemented soft dictionaries (to address os.hashid issue)
- Implemented character delete (no timer)
- Implemented simple cached methods (no arguments, return cached objects)
- Fixed agent listing.
- Fixed issue with boot-on-demand systems and NPC spawning.
- Fixed several memory leaks

0.5.153:
- Implemented an initial NPC spawn system, supporting static spawns with possibly randomized locations.
- Fixed ship display while in space.
- Fixed a few cache related issues in order to support NPCs.
- Implemented the beginings of an inventory system, supporting items and their attributes.
- Added custom build tool to win32 project to support xml packet generation
- Several patches from the forums.

