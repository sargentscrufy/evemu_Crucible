-- ------------------------------------------------------------------------
-- Market Seed v2 — hub-weighted bootstrap with NPC buy walls
-- ------------------------------------------------------------------------
-- Design: doc/design/market-economy.md.  Replaces seed_market.sql.
--
-- Per seeded region:
--   * one HUB station (the station in the region's most-stationed system):
--     full catalog sell orders at deep stock, base-price +0..10%;
--     NPC BUY WALLS for minerals / ore / salvage / PI goods at 85% of base
--     (the "Jita magnet" that future hauler bots and players sell into).
--   * FRINGE stations (random @saturation share of the rest): essential
--     categories at ~1/10 hub stock, sell prices +10..25% over base
--     (goods are dearer on the fringe -> haul from hub for profit);
--     buy walls for ore/minerals only, at 70% of base (raw materials are
--     cheaper on the fringe -> haul to hub for profit).
--
-- NPC buy orders use per-region trader IDs (minTrader 4000001..maxTrader
-- 5000000, EVE_Defines.h); MarketMgr::ExecuteBuyOrder treats traders as
-- item sinks and keeps journal entries.  escrow MUST be price*qty or
-- players cannot sell into the order (see MarketBotMgr::PlaceBuyOrders).
--
-- Expects the caller (db_init.sh or manual run) to provide:
--   CREATE TEMPORARY TABLE tSeedRegions (regionName VARCHAR(100));
--   INSERT INTO tSeedRegions VALUES ('The Forge'), (...);
--   SET @saturation = 0.5;   -- share of non-hub stations to stock (0..1)
--
-- Idempotent-ish: re-running first deletes previous NPC-seeded orders
-- (NPC corp sells, trader-range buys); player orders are never touched.
-- ------------------------------------------------------------------------

SET @saturation = IFNULL(@saturation, 0.5);
-- Windows FILETIME "now" and one day, as used by mktOrders.issued
SET @ftNow = (UNIX_TIMESTAMP() + 11644473600) * 10000000;
SET @ftDay = 864000000000;

-- ---------------------------------------------------------------- regions
DROP TEMPORARY TABLE IF EXISTS tRegions;
CREATE TEMPORARY TABLE tRegions AS
SELECT r.regionID,
       -- per-region NPC trader, inside [minTrader, maxTrader]
       (4000001 + (r.regionID - 10000000)) AS traderID
FROM mapRegions r
JOIN tSeedRegions s ON r.regionName = s.regionName;

-- clean previous NPC seed (never touches player orders: chars are 90M+,
-- player corps are far outside the NPC corp 1.0-2.0M band)
DELETE FROM mktOrders
 WHERE regionID IN (SELECT regionID FROM tRegions)
   AND ((bid = 0 AND ownerID BETWEEN 1000000 AND 2000000)
     OR (bid = 1 AND ownerID BETWEEN 4000001 AND 5000000));
DELETE FROM mktHistory WHERE regionID IN (SELECT regionID FROM tRegions);

-- ------------------------------------------------------------------- hubs
DROP TEMPORARY TABLE IF EXISTS tHubs;
CREATE TEMPORARY TABLE tHubs AS
SELECT regionID, stationID, solarSystemID, corporationID
FROM (
    SELECT st.regionID, st.stationID, st.solarSystemID, st.corporationID,
           ROW_NUMBER() OVER (
               PARTITION BY st.regionID
               ORDER BY sc.cnt DESC, st.security DESC, st.stationID
           ) AS rn
    FROM staStations st
    JOIN (SELECT solarSystemID, COUNT(*) cnt
          FROM staStations GROUP BY solarSystemID) sc USING (solarSystemID)
    JOIN tRegions USING (regionID)
) ranked
WHERE rn = 1;

-- ----------------------------------------------------------------- fringe
DROP TEMPORARY TABLE IF EXISTS tFringe;
CREATE TEMPORARY TABLE tFringe AS
SELECT st.regionID, st.stationID, st.solarSystemID, st.corporationID
FROM staStations st
JOIN tRegions USING (regionID)
LEFT JOIN tHubs h USING (stationID)
WHERE h.stationID IS NULL
  AND RAND() < @saturation;

-- ------------------------------------------------------- sellable catalog
-- categories: 4 Material, 5 Accessories, 6 Ship, 7 Module, 8 Charge,
-- 9 Blueprint, 16 Skill, 17 Commodity, 18 Drone, 20 Implant,
-- 22 Deployable, 24 Reaction, 25 Asteroid(ore), 32 Subsystem,
-- 35 Decryptors, 42/43 Planetary
DROP TEMPORARY TABLE IF EXISTS tTypes;
CREATE TEMPORARY TABLE tTypes AS
SELECT t.typeID, g.categoryID, g.groupID,
       IF(t.basePrice <= 0, 100, t.basePrice) AS effBase,
       CASE g.categoryID
           WHEN 4  THEN 2000000  -- minerals/materials: manufacturing fuel
           WHEN 5  THEN 1000
           WHEN 6  THEN 50       -- ships
           WHEN 7  THEN 1000     -- modules
           WHEN 8  THEN 500000   -- charges/ammo
           WHEN 9  THEN 25       -- blueprints
           WHEN 16 THEN 5000     -- skills
           WHEN 17 THEN 10000
           WHEN 18 THEN 5000     -- drones
           WHEN 20 THEN 500      -- implants
           WHEN 22 THEN 200
           WHEN 24 THEN 500
           WHEN 25 THEN 500000   -- ore (sellable stock for refiners)
           WHEN 32 THEN 100
           WHEN 35 THEN 200
           WHEN 42 THEN 10000
           WHEN 43 THEN 10000
           ELSE 500
       END AS hubQty
FROM invTypes t
JOIN invGroups g USING (groupID)
WHERE t.published = 1
  AND g.categoryID IN (4,5,6,7,8,9,16,17,18,20,22,24,25,32,35,42,43);

-- --------------------------------------------------------- hub sell orders
INSERT INTO mktOrders
    (typeID, ownerID, regionID, stationID, solarSystemID, orderRange, bid,
     price, escrow, minVolume, volEntered, volRemaining, issued, duration,
     jumps, isCorp, accountKey, memberID)
SELECT ty.typeID, h.corporationID, h.regionID, h.stationID, h.solarSystemID,
       32767, 0,
       ROUND(ty.effBase * (1.00 + RAND() * 0.10), 2), 0, 1,
       ty.hubQty, ty.hubQty,
       @ftNow - FLOOR(RAND() * 14) * @ftDay,
       90 + FLOOR(RAND() * 275), 1, 0, 1000, 0
FROM tHubs h
CROSS JOIN tTypes ty;

-- ------------------------------------------------------ fringe sell orders
-- essentials only, thinner stock, +10..25% over base
INSERT INTO mktOrders
    (typeID, ownerID, regionID, stationID, solarSystemID, orderRange, bid,
     price, escrow, minVolume, volEntered, volRemaining, issued, duration,
     jumps, isCorp, accountKey, memberID)
SELECT ty.typeID, f.corporationID, f.regionID, f.stationID, f.solarSystemID,
       32767, 0,
       ROUND(ty.effBase * (1.10 + RAND() * 0.15), 2), 0, 1,
       GREATEST(1, FLOOR(ty.hubQty / 10)), GREATEST(1, FLOOR(ty.hubQty / 10)),
       @ftNow - FLOOR(RAND() * 14) * @ftDay,
       90 + FLOOR(RAND() * 275), 1, 0, 1000, 0
FROM tFringe f
CROSS JOIN tTypes ty
WHERE ty.categoryID IN (4,6,7,8,16,17,18,25);

-- ------------------------------------------------------------- buy walls
-- what NPCs buy: minerals (group 18), ore (cat 25), salvage (754/966),
-- planetary goods (42/43)
DROP TEMPORARY TABLE IF EXISTS tBuyTypes;
CREATE TEMPORARY TABLE tBuyTypes AS
SELECT ty.typeID, ty.categoryID, ty.groupID, ty.effBase,
       CASE
           WHEN ty.groupID = 18            THEN 10000000 -- minerals
           WHEN ty.categoryID = 25         THEN 2000000  -- ore
           WHEN ty.groupID IN (754, 966)   THEN 50000    -- salvage
           WHEN ty.categoryID IN (42, 43)  THEN 200000   -- planetary
       END AS hubBuyQty
FROM tTypes ty
WHERE ty.groupID IN (18, 754, 966)
   OR ty.categoryID IN (25, 42, 43);

-- hub buy walls: 85% of base, solar-system range (sell it AT the hub —
-- this is what makes hauling raw materials hub-ward profitable)
INSERT INTO mktOrders
    (typeID, ownerID, regionID, stationID, solarSystemID, orderRange, bid,
     price, escrow, minVolume, volEntered, volRemaining, issued, duration,
     jumps, isCorp, accountKey, memberID)
SELECT bt.typeID, r.traderID, h.regionID, h.stationID, h.solarSystemID,
       0, 1,
       ROUND(bt.effBase * 0.85, 2),
       ROUND(bt.effBase * 0.85, 2) * bt.hubBuyQty,   -- escrow: mandatory
       1, bt.hubBuyQty, bt.hubBuyQty,
       @ftNow - FLOOR(RAND() * 7) * @ftDay,
       90 + FLOOR(RAND() * 275), 1, 0, 1000, 0
FROM tHubs h
JOIN tRegions r USING (regionID)
CROSS JOIN tBuyTypes bt;

-- fringe buy walls: ore/minerals only, 70% of base, thin
INSERT INTO mktOrders
    (typeID, ownerID, regionID, stationID, solarSystemID, orderRange, bid,
     price, escrow, minVolume, volEntered, volRemaining, issued, duration,
     jumps, isCorp, accountKey, memberID)
SELECT bt.typeID, r.traderID, f.regionID, f.stationID, f.solarSystemID,
       0, 1,
       ROUND(bt.effBase * 0.70, 2),
       ROUND(bt.effBase * 0.70, 2) * GREATEST(1, FLOOR(bt.hubBuyQty / 10)),
       1, GREATEST(1, FLOOR(bt.hubBuyQty / 10)),
       GREATEST(1, FLOOR(bt.hubBuyQty / 10)),
       @ftNow - FLOOR(RAND() * 7) * @ftDay,
       90 + FLOOR(RAND() * 275), 1, 0, 1000, 0
FROM tFringe f
JOIN tRegions r USING (regionID)
CROSS JOIN tBuyTypes bt
WHERE bt.groupID = 18 OR bt.categoryID = 25;

-- ------------------------------------------------- price history backfill
-- 14 days of plausible history per (region, type) so charts render
INSERT INTO mktHistory
    (regionID, typeID, historyDate, lowPrice, highPrice, avgPrice, volume, orders)
SELECT r.regionID, ty.typeID,
       @ftNow - d.n * @ftDay,
       ROUND(ty.effBase * 0.95, 2),
       ROUND(ty.effBase * 1.10, 2),
       ROUND(ty.effBase * (0.98 + RAND() * 0.06), 2),
       GREATEST(1, FLOOR(ty.hubQty / 10 * (0.5 + RAND()))),
       3 + FLOOR(RAND() * 15)
FROM tRegions r
CROSS JOIN tTypes ty
CROSS JOIN (
    SELECT 1 n UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
    UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8
    UNION SELECT 9 UNION SELECT 10 UNION SELECT 11 UNION SELECT 12
    UNION SELECT 13 UNION SELECT 14
) d;

-- ------------------------------------------------------------------ report
SELECT 'hubs' AS what, COUNT(*) AS cnt FROM tHubs
UNION ALL
SELECT 'fringe stations', COUNT(*) FROM tFringe
UNION ALL
SELECT 'sell orders', COUNT(*) FROM mktOrders WHERE bid = 0
    AND ownerID BETWEEN 1000000 AND 2000000
UNION ALL
SELECT 'buy orders', COUNT(*) FROM mktOrders WHERE bid = 1
    AND ownerID BETWEEN 4000001 AND 5000000
UNION ALL
SELECT 'history rows', COUNT(*) FROM mktHistory;
