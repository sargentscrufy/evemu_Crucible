# Human client playtest — objectives & feedback form

**Server:** local docker EVEmu Crucible (game port **26010**, or **26000** if the debug proxy is up)  
**Client:** EVE Online Crucible build **360229**  
**Date prepared:** 2026-08-03  
**Build notes (2026-08-02/03 playtest polish):** soft warp land + grid keep mid-warp; TURN-1 approach turns; jump cloak ~30s / login cloak ~20s; gun FX mid-fight; belt rats ≤0.9 free-fire; drones engage/return/bay; Local MOTD + login modal. Market + security missions still in tree.

---

## Before you start

1. Confirm server is healthy (`docker ps` → `server` healthy).
2. Point client `serverName` at the host IP (port is hardwired **26000** on the client — use the proxy or publish 26000).
3. Log in with a normal pilot (or TEMPORARY test account if injected).
4. Have Local chat ready: type reports as  
   `BUG short description of what happened`  
   (uppercase **BUG** is required for capture).

---

## Objectives (do in order when possible)

### A. Session basics (5 min)
| # | Objective | Pass if… | Your notes (Y/N + comment) |
|---|---|---|---|
| A1 | Log in, load into station or space | No freeze/crash | |
| A2 | Read MOTD / patch notes if shown | Dialog appears or N/A | |
| A3 | Undock; cap+shield full; throttle any (100% full burn is **approved**) | No fling / freeze; thrusters respond | |
| A4 | Dock again | Clean dock, no “stuck warping” | |

### B. Travel & destiny (10 min)
| # | Objective | Pass if… | Notes |
|---|---|---|---|
| B1 | Warp to a belt or planet | Lands near object, not inside | |
| B2 | Warp to a stargate and jump | Session hands off; you appear in next system | |
| B3 | Stop / Align / Warp again after a short hop | No permanent Dock/Warp lockout | |
| B4 | If you hit a ship/structure, you are **not** punted off-grid | Stay on overview grid | |

### C. Music & audio — **priority this session** (10 min)
| # | Objective | Pass if… | Notes |
|---|---|---|---|
| C1 | In open space / station undock, ambient music plays | Hear ambient | |
| C2 | Accept a **security mission**, warp to the site (gate room) | Hear **combat / dungeon** music (or note if still ambient) | |
| C3 | Activate acceleration gate into the pocket | Music stays combat / intensifies; hostiles on overview | |
| C4 | Engage rats (lock + fire) | Weapon beams/sounds; combat music if not already | |
| C5 | After combat ends / dock | Music returns toward ambient (or note sticky combat track) | |

**What to write for music bugs:**  
`BUG music still ambient in mission pocket after gate` / `BUG no combat music when rats aggro in belt`

### D. Security mission full loop (15–20 min)
| # | Objective | Pass if… | Notes |
|---|---|---|---|
| D1 | Agent offers encounter mission with readable **title + briefing prose** | Not a wrong type-ID name | |
| D2 | Journal / right-click shows **mission location** / warp option | Can warp to site without guessing | |
| D3 | Gate room: gate visible; pocket not cluttering room-1 overview | Two-room feel | |
| D4 | Pocket: leader taunt (notification or local), escorts shoot back | Fight feels alive | |
| D5 | Kill transport; loot objective container; return & complete | Reward + bonus if in time | |
| D6 | Time bonus display not “already expired” at accept | Bonus timer sensible | |

### E. Market & industry smoke (10 min)
| # | Objective | Pass if… | Notes |
|---|---|---|---|
| E1 | Open market **docked** — orders visible | Not empty book | |
| E2 | Open market **in space** — still browsable | Not empty tree | |
| E3 | Buy something cheap; items appear in hangar | No missing stack | |
| E4 | Optional: reprocess or start a simple manufacture job | Completes or clear error | |

### F. Combat polish (10 min)
| # | Objective | Pass if… | Notes |
|---|---|---|---|
| F1 | Turret fire shows beams / hits | Visible FX | |
| F2 | Rats return fire when you shoot first | Not silent NPCs | |
| F3 | Optional: smartbomb pulse damages nearby junk/rats | AoE works | |
| F4 | Optional: warp scramble a target (or get scrambled) | Warp blocked while pointed | |

### G. Stability (throughout)
| # | Objective | Pass if… | Notes |
|---|---|---|---|
| G1 | No client hard crash | Session stays up | |
| G2 | No “server closed connection” / forced disconnect | | |
| G3 | Relog mid-session works | Character intact | |

---

## Feedback channels (use all that apply)

1. **In-game Local:** `BUG …` lines (auto-logged to `feedback.log`).  
2. **This form:** fill the tables (Y/N + short comment).  
3. **Screenshots:** music UI not needed; for empty market, missing journal warp, wrong titles, FX.  
4. **After session:** ask the dev AI to pull  
   `docker cp server:/app/server_cache/feedback.log …/feedback-inbox/feedback-YYYYMMDD-HHMMSS.log`

---

## Severity guide for your notes

| Tag | Meaning |
|---|---|
| **BLOCKER** | Cannot play core loop (crash, cannot dock, mission uncompletable) |
| **MAJOR** | Wrong music at site, market empty undocked, silent rats, no mission location |
| **MINOR** | Gate facing, cosmetic slim, small timer text |
| **NICE** | QoL suggestion |

---

## Suggested 45-minute path

1. A → B (session + travel)  
2. C + D (music + full security mission) — **highest value this build**  
3. E market smoke  
4. F if time  
5. Paste Local BUG lines + this checklist back to the dev session  

---

## Known soft spots (don’t over-report as new)

- **Align timeout:** server may log `warp align/speed is incorrect, but time > shipTimeToWarp` then force warp — travel still works.  
- **Login client noise:** Neocom skill `TypeError: float()`, occasional `No ballpark` / `GetBalls` — usually non-fatal.  
- **Redeploy ≠ crash:** if the server “dies” mid-session after a code push, check exit 143 (SIGTERM) vs real segfault.  
- Hunt bot kill cert still soft (human kill in missions works).  
- Destroyable belt asteroids for gun testing (intentional).  
- Invention / T2 not implemented.
- NAV autopilot one-click chain still broken.  
- Faction police undock-from-hostile-home incomplete.  

Report if any of these **regressed** or feel worse than last session.

---

## Sign-off

| Field | Value |
|---|---|
| Pilot name | |
| Session start/end | |
| Overall feel (1–5) | |
| Top 3 issues | |
| Music verdict (C2–C5) | |
| OK to stage next release? (Y/N) | |
