# Market Seeding & Ambient Economy — Evaluation and Direction

**Status:** Analysis (2026-07-08). No code changes yet.
**Question:** is the current `SEED_MARKET` mechanism the right way to seed
the market, and what would better look like?

## What exists today

Three disconnected layers:

1. **One-shot SQL seed** (`SEED_MARKET=TRUE` → evedbtool `seed` at first
   DB init; logic mirrors `sql/seed_and_clean/seed_market.sql`): for a
   random `SEED_SATURATION`% of stations in `SEED_REGIONS`, insert one
   **sell order per published item type** (22 categories) with:
   - quantity **550 for everything** (550 battleships per backwater station)
   - price = `basePrice / security` (see defects)
   - hardcoded `issued` timestamp (~2020), 250-day duration
   - **zero buy orders**
2. **MarketMgr live loop:** `SetBasePrice()` / `UpdateMineralPrice()` /
   `UpdatePriceHistory()` — recalculates base prices from mineral values
   and maintains price history for traded items.
3. **MarketBotMgr ("Trader Joe"):** runs unconditionally when
   `MarketBot.xml` parses (minute tick via EntityList). Expires old bot
   orders and places buy/sell orders in eligible systems per its config
   (group whitelist, order lifetime, price ranges).

## Verdict: the seed is a bootstrap, not an economy — and it has defects

**Defects in the SQL seed itself:**

- **D1 — No buy orders.** Players can sell nothing except to other
  players. Mining/ratting loot has no ISK sink; the core PvE income loop
  is broken on a private server with no population.
- **D2 — `price = basePrice / security` is wrong at the edges.** Nullsec
  security ≤ 0 → negative or divide-by-zero prices (the `price=100 WHERE
  price=0` patch only catches exact zero). Lowsec (0 < sec < 1) *raises*
  prices — backwards from EVE's economics, where hubs are expensive to
  reach, not high-sec.
- **D3 — Uniform quantity 550** for ammo and capital ships alike. No
  trade-hub structure: every seeded station is an identical supermarket,
  so there is no reason to travel, haul, or trade.
- **D4 — Stale metadata.** `issued` hardcoded to ~2020, all orders share
  one timestamp and a 250-day duration → mass simultaneous expiry, and
  price-history charts start empty (nothing writes mktHistory at seed).
- **D5 — One-shot.** Bought-out orders never restock. The market decays
  monotonically from the moment the server starts.

**Structural point:** even a perfect one-shot seed decays. A market that
*feels alive* needs a continuous actor, not a better INSERT. That actor
already half-exists (Trader Joe) — the seed and the bot just don't know
about each other.

## Recommended direction: NPC market-maker model

Treat the market as three cooperating parts, matching plan.md Tier 1:

### 1. Smarter bootstrap (fix the seed; keep it one-shot and dumb)
- Category-aware quantities (ammo 10⁴–10⁵, modules 10², ships 5–50,
  skills large-qty at fixed price in school stations — Crucible-accurate).
- Price = `basePrice × jitter(0.9–1.15) × regional modifier`; clamp
  security factor to `max(0.5, security)`; never divide by ≤0.
- **Hub weighting:** designate one major hub per region (+ minor hubs);
  hubs get full catalogs and deep stock, other stations get a thin
  regional subset. Travel and hauling become meaningful.
- Seed **NPC buy orders** for ore, minerals, salvage, and common loot at
  ~70–85% of sell price → players can always cash out.
- `issued = now`, staggered durations; backfill ~30 days of plausible
  mktHistory so charts render.

### 2. Continuous market maker (extend Trader Joe's mandate)
- Restock toward target inventory levels per (station, type) on its
  existing cycle instead of placing unrelated random orders.
- Maintain the buy-side wall (ore/minerals/loot) as orders fill.
- Price movement: random walk + demand response (sales push price up,
  unsold stock drifts down), writing mktHistory via the existing
  MarketMgr machinery. Bounded by min/max multipliers of base price.
- Config: per-category stock/price policy in MarketBot.xml rather than
  hardcoded groups.

### 3. Director-driven trade (Phase 3, later)
- Tier-2 hauler bots physically move goods hub-to-hub; regional price
  differences become real arbitrage the human player can compete with.
- The AI Director sets regional supply/demand shocks (events from the
  web GUI: "mineral shortage in Derelik this week").

### Where the code lives
Steps 1–2 extend existing seams (evedbtool seed SQL + MarketBotMgr +
MarketMgr price loop) — acceptable in-process per plan.md since the
machinery already exists. Step 3 is external Director work. The web GUI
gets read/control endpoints later (market depth dashboard, stock policy
tuning, event injection).

### Housekeeping found during analysis
- Boot logs show config drift: `Unknown element 'UseMarketBot'` (and
  others) — the shipped eve-server.xml carries elements the built server
  no longer parses. Needs a config-version reconciliation pass.
- MarketBot runs whenever its XML parses — there is no master enable
  switch; verify its current defaults are sane for a fresh server.
