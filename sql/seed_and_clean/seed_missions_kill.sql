-- SECMISSION-1: L1 security (encounter) mission content.
-- Loaded by MissionDB::LoadKillData at boot; offered by Security /
-- Internal Security / Intelligence division agents.
-- typeID 2 = Mission::Type::Encounter.  itemTypeID is the goal item the
-- pilot recovers from the guarded site (Militants 25373, Marines 3810,
-- Reports 3814).  briefingID reuses a retail courier text id until we
-- source retail security briefing ids (cosmetic; objectives are correct).

CREATE TABLE IF NOT EXISTS qstKill LIKE qstCourier;

DELETE FROM qstKill;
INSERT INTO qstKill (id, briefingID, name, level, typeID, important, storyline,
    itemTypeID, itemQty, rewardISK, rewardItemID, rewardItemQty, bonusISK,
    bonusTime, sysRange, raceID) VALUES
  (56001, 130400, 'Pirate Ambush',         1, 2, 0, 0, 25373, 1, 120000, 0, 0, 60000, 1800, 0, 0),
  (56002, 130400, 'Retrieve the Reports',  1, 2, 0, 0, 3814,  1, 140000, 0, 0, 70000, 1800, 0, 0),
  (56003, 130400, 'Hostage Rescue',        1, 2, 0, 0, 3810,  2, 160000, 0, 0, 80000, 1800, 0, 0),
  (56004, 130400, 'Cut the Supply Line',   1, 2, 0, 0, 25373, 2, 150000, 0, 0, 75000, 1800, 0, 0),
  (56005, 130400, 'Silence the Informant', 1, 2, 0, 0, 3814,  1, 180000, 0, 0, 90000, 1800, 0, 0);
