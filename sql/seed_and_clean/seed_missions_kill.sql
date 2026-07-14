-- SECMISSION-M2/M3: L1 security (encounter) mission content.
-- Loaded by MissionDB::LoadKillData at boot; offered by Security /
-- Internal Security / Intelligence division agents.
--
-- typeID 2 = Mission::Type::Encounter.  itemTypeID is the goal item the pilot
-- recovers from the site (Militants 25373, Marines 3810, Reports 3814).
--
-- SECMISSION-M2 moved mission prose OUT of a hardcoded C++ switch and into two
-- TEXT columns, so text is content rather than code and can be rewritten
-- without rebuilding the server:
--
--   briefing    -- the journal description.  Served to the client as a PyString
--                  via briefingTextID for custom missions (id >= 56000), the
--                  same mechanism already proven for missionNameID titles.
--                  briefingID is retained purely as a numeric fallback.
--   leaderLine  -- what the site's Guristas leader says when the pilot warps in.
--
-- The fiction is pinned to what SpawnMissionSite actually builds: a deadspace
-- site off a planet in the AGENT'S OWN system, held by Guristas -- a leader
-- (Pithi Wrecker), 2-4 Pithi frigates, and a Guristas Hauler that is carrying
-- the objective.  The hauler's WRECK holds the goal item, so the flow is
-- "kill the escort, kill the hauler, loot it, fly home".
--
-- IF THE SPAWN MODEL CHANGES, THESE BRIEFINGS MUST CHANGE WITH IT.  A briefing
-- that describes a site the server does not build is worse than no briefing.
--
-- L1 is meant to be easy: light frigates, no webs or scrams, one soft transport.

DROP TABLE IF EXISTS qstKill;
CREATE TABLE qstKill LIKE qstCourier;
ALTER TABLE qstKill
    ADD COLUMN briefing   TEXT NULL AFTER briefingID,
    ADD COLUMN leaderLine TEXT NULL AFTER briefing;

INSERT INTO qstKill (id, briefingID, briefing, leaderLine, name, level, typeID,
    important, storyline, itemTypeID, itemQty, rewardISK, rewardItemID,
    rewardItemQty, bonusISK, bonusTime, sysRange, raceID) VALUES

  (56001, 130400,
   'Two days ago the freighter <b>Kaalakiota Dawn</b> dropped out of warp in this system and never made her next checkpoint. We know why now. A Guristas raiding wing ambushed her, cut her engines, and boarded.\n\nThey killed her crew and stripped the hold. What they took matters more than the cargo -- her encoded flight logs, which record every waypoint and every contact on her route. In Guristas hands, those logs are a map of our shipping lanes.\n\nThe raiders have not left. They are holding in a deadspace pocket off one of the planets in this system, moving their haul onto a Guristas Hauler. Warp in, break the escort, and <b>destroy that hauler before it can move the logs.</b> Pull the reports out of the wreck and bring them to me.\n\nIt is a light wing. A handful of frigates. You will manage.',
   'Well. The State sent one ship. I have your freighter''s logs, pilot -- every lane, every contact, every fat little convoy you people run. Pity you will not live to carry them home.',
   'Recover the Freighter Logs', 1, 2, 0, 0, 3814, 1, 140000, 0, 0, 70000, 60, 0, 0),

  (56002, 130400,
   'A Guristas snatch team hit a personnel transport on the edge of this system and took the survivors alive. That is not mercy. It is inventory. They sell what they capture.\n\nWe have tracked them to a deadspace pocket off a planet in this system. Our people are aboard a Guristas Hauler, still sitting alongside the transport they gutted.\n\nClear the escorting frigates, then <b>destroy the hauler and recover our crew from the wreckage.</b> Move. Once that hauler aligns out, we will never see them again.',
   'Cargo is cargo, and people sell better than ore. Take your shot if you like -- you will only be shooting your own.',
   'Rescue the Transport Crew', 1, 2, 0, 0, 3810, 2, 160000, 0, 0, 80000, 60, 0, 0),

  (56003, 130400,
   'The Guristas have been running a resupply line through this system for weeks, and we have finally caught the tail of it. A supply hauler is holding in a deadspace pocket off one of the local planets with a light frigate escort, waiting on a rendezvous that is not going to happen.\n\n<b>Kill the escort, then kill the hauler.</b> The militants riding shotgun on it are what we want -- pull them out of the wreck and bring them in for questioning.\n\nCut this line and their operations in this constellation go quiet for a month.',
   'You are late, and you are alone. Neither of those is a good look on a man. Burn him.',
   'Cut the Supply Line', 1, 2, 0, 0, 25373, 2, 150000, 0, 0, 75000, 60, 0, 0),

  (56004, 130400,
   'One of our field operatives was compromised. Before we could extract him, a Guristas wing pulled him out of his ship alive -- along with the intelligence dossier he was carrying.\n\nThey are holding in deadspace off a planet in this system, waiting on a buyer. That dossier names every asset we run in this region. It does not get sold.\n\nDestroy the escort. <b>Destroy the hauler holding the dossier and recover the reports.</b> Whatever else happens out there, those reports come back with you.',
   'The State pays well for silence, pilot. Their enemies pay faster. Put him down and we make the drop on schedule.',
   'Silence the Informant', 1, 2, 0, 0, 3814, 1, 180000, 0, 0, 90000, 60, 0, 0),

  (56005, 130400,
   'A Guristas press gang has been working this system, pulling crews off civilian haulers and pressing them into their own ranks. We have a fix on their staging point -- a deadspace pocket off one of the planets in this system.\n\nThey have a hauler out there loaded with the people they have rounded up, behind a light frigate screen. <b>Clear the screen, kill the hauler, and recover the militants from the wreck.</b>\n\nMost of them are not soldiers. They are dockworkers who drew the wrong shift. Bring them home.',
   'Fresh meat for the fleet, and here comes another volunteer. Wrap him up.',
   'Break the Press Gang', 1, 2, 0, 0, 25373, 1, 120000, 0, 0, 60000, 60, 0, 0);

-- SECMISSION-M4: L2 tier -- Pithum cruisers stiffen the escort (SpawnMissionSite
-- scales by qstKill.level).  Offered by level-2 Security division agents.
INSERT INTO qstKill (id, briefingID, briefing, leaderLine, name, level, typeID,
    important, storyline, itemTypeID, itemQty, rewardISK, rewardItemID,
    rewardItemQty, bonusISK, bonusTime, sysRange, raceID) VALUES

  (56011, 130400,
   'This is not a raider picket, pilot. A Guristas convoy escort went rogue with its cargo -- a hauler full of classified transponder codes stripped from three of our patrol wings. They are holding in a deadspace pocket in this system behind a proper escort: cruisers, not the usual frigate rabble.\n\nTake the acceleration gate in, break the escort, and <b>destroy the hauler before those codes reach a buyer.</b> Recover the reports from the wreck and bring them home.\n\nBring a real ship. This one bites back.',
   'Cruisers on the field and the State still sends one hull. I will mount you next to the last one. Kill him.',
   'Rogue Escort', 2, 2, 0, 0, 3814, 2, 320000, 0, 0, 160000, 60, 0, 0),

  (56012, 130400,
   'A Guristas slaver wing has been sweeping the outer belts, and this time they took an entire mining crew -- fourteen of our people, held aboard a hauler in a guarded deadspace pocket in this system.\n\nThe escort is cruiser-class. Punch through it, <b>destroy the hauler, and pull our miners out of the wreckage.</b> Every hour they sit out there is an hour closer to a slave market in Venal.\n\nThe State does not leave its people behind. Neither do you.',
   'Fourteen head of cargo, and now a hero to feed to the escort. Today keeps getting better.',
   'Leave No One Behind', 2, 2, 0, 0, 3810, 4, 350000, 0, 0, 175000, 60, 0, 0);
