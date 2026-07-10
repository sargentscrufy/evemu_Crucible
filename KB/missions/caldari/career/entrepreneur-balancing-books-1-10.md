# Entrepreneur - Balancing the Books (1-10) - Full Intro Hauling/Salvage/Mining/Hacking Career Arc (2009-2014)

**Agent / Corp / Location**: Industrialist - Entrepreneur career agent. Caldari examples: Science and Trade Institute (STI) or Sukuuvestaa (or similar school corps) stations e.g. Jouvulen, Akiainavas. High-sec Caldari space. L1 intro career.

**Briefing / Story**: Corporate Caldari "business mogul" training vs Guristas pirate threat. Progressive: transport sensitive data, salvage black box from destroyed transport, mine/reprocess, destroy Guristas surveillance outpost + hack, long courier for decryption, procure modules for security forces, clear ancient staging site + relic analyze, courier evidence for funding, supply afterburners, finally build weapons. Themes of national security, business acumen feeding "war machine". Ends with hauler reward and advice to distribution agents.

**Objectives / Exact Steps** (verbatim era structure from 2011-2014 guides; Caldari flavor with Guristas encounters; locations agent-specific):

1. **Balancing the Books (1 of 10)**: Safely transport Data Sheets (national security files). Haul 1 jump (or short distance). Put in cargohold, deliver to destination station, report back.  
   **Reward**: ISK.

2. **Balancing the Books (2 of 10)**: Locate destroyed transport ship wreckage in deadspace (acceleration gate). Kill lingering Guristas hostiles (e.g. Guristas Rookie). Use provided Civilian Salvager on Civilian Transport Ship Wreck to extract Black Box. Return Black Box.  
   **Reward**: Venture, Civilian Salvager, ISK.  
   **Notes**: Combat + salvage. Deadspace pocket.

3. **Balancing the Books (3 of 10)**: Warp to coordinates (Veldspar asteroids). Mine Veldspar with Venture (fit miner + turret for pirates). Return and reprocess to ~333 Tritanium. Deliver Tritanium.  
   **Reward**: Miner I, Reprocessing Skillbook, ISK.

4. **Balancing the Books (4 of 10)**: Destroy Guristas surveillance/listening post outpost and defending vessels. Hack Data Storage Device with Civilian Data Analyzer to retrieve Encoded Data Chip. Clear area, loot chip.  
   **Reward**: Civilian Data Analyzer, ISK.  
   **Notes**: Deadspace gates. Guristas pirates. Hacking minigame (minesweeper-style).

5. **Balancing the Books (5 of 10)**: Ferry Encoded Data Chip (heavily encoded tactical info) safely ~9 jumps to contact (e.g. Uoyonen IX - Perkone Warehouse, varies by agent).  
   **Reward**: Inertial Stabilizer I, Expanded Cargohold I, ISK.  
   **Notes**: Long courier; use stabilizers.

6. **Balancing the Books (6 of 10)**: Procure 1 x Civilian Armor Repairer (buy on market from sellers, or other means) for security forces shortage.  
   **Reward**: Broker Relations Skillbook, Nanofiber Internal Structure I, ISK.  
   **Notes**: Business acumen test; market buy common.

7. **Balancing the Books (7 of 10)**: Clear ancient site staging outpost used by Guristas (multiple pockets/gates). Kill 2 sets of NPCs/pirates. Use Civilian Relic Analyzer on ancient ships/ruins/Ancient Ship Structure. Loot results.  
   **Reward**: Civilian Relic Analyzer, 1MN Afterburner, ISK.  
   **Notes**: Relic hacking minigame.

8. **Balancing the Books (8 of 10)**: Courier Central Data Core (compiled evidence from prior ops) 1 jump to contact (e.g. Unpas VI - Moon 10 - Core Complexion Inc. Storage).  
   **Reward**: Limited Social Implant, ISK.

9. **Balancing the Books (9 of 10)**: Deliver 2 x 1MN Afterburner I (buy, build from prior BPs, or repackage rewards/loot).  
   **Reward**: ISK (plus modules referenced).  
   **Notes**: Supply frigate contingents.

10. **Balancing the Books (10 of 10)**: Fulfill quota: build small gun (e.g. using provided BPC; any extra runs yours). Deliver.  
    **Reward**: Extra Small gun BPC, Hauler (Badger), ISK.  
    **Debrief**: "Well done, Ship Type. Here is your Badger, as promised; use it well. You've completed all my tasks and shown yourself to be a savvy entrepreneur."

**Rewards / LP / Bounty notes (era)**: Ships (Venture, Badger), modules (miners, cargo, ABs, nanofibers, stabilizers, analyzers, salvager, data/relic), skillbooks (Reprocessing, Broker Relations), ISK, implant. Progressive unlocks for hauling/mining/hacking/combat/industry. Guristas bounties/loot incidental.

**Strategy / Approach Loops**: 
- Core loop: Courier (drag to cargo, set dest via agent or manual, jump/dock/turn-in), Combat+Salvage/Hack (gate, kill small Guristas frigs, use module on can/wreck), Mine+Reprocess, Market buy for shortcuts, Build (industry job).
- Combat: Simple Guristas (Rookie, small groups); civilian guns, orbit, AB. Deadspace accel gates.
- Optimize: Repackage tricks for free fittings; buy cheap items vs build/mine when time-sensitive; overlap with AIR if active; use overview/keyboard for efficiency.
- Hacking: Minesweeper minigame for data/relic analyzers.
- Locations: Agent-uploaded bookmarks; 1 jump early, long burns mid-arc (varies 1-9 jumps Caldari highsec); deadspace pockets for combat/hack/salvage.

**Era Notes / Caldari Flavor**: Classic L1 career intro teaching core loops (haul, mine, salvage, hack, build, light combat) in context of Caldari State vs Guristas piracy. "Balancing the Books" corporate espionage/security vs pirates storyline. Rewards build self-sufficiency (Venture for mine, Badger for haul). Matches 2009-2014 career agents (STI etc.). Run in parallel with Producer arc for full industrial intro. Low risk, educational.

**Sources**: 
- https://www.wckg.net/Newbie/career-agents (full verbatim briefings/goals fetched)
- Cross-ref: wiki.eveuniversity.org/Industrialist_(Entrepreneur), era guides (tentonhammer, eve-search era posts)
- Raw full transcript in scratch/sources/entrepreneur-balancing-books-1-10.txt
- SQL: agtMissions has 'Balancing the Books (1 of 10)' entries.

**SQL Cross-Check**: Excerpts in scratch/sql/. Titles confirmed in agtMissions dump. Career agents in school corps (STI/SAK etc.). No complex encounters table as these are simple L1 objectives.

**Notes for EvEmu rebuild**: Implement as chained career missions with journal entries matching exact briefings above. Objectives: item transport (qty/volume), kill+salvage specific wrecks, mine quota + reprocess, kill + analyzer hack on structures, simple courier, market procure (or build), kill + relic, build item from BPC. Use existing agent/mission systems (agt*, qst*). Rewards scripted per step. Guristas NPC spawns minimal (frigs). Deadspace via dungeons or simple pockets. Agent locations in Caldari highsec rookie systems.
