# Mission QA Findings (courier arc) — 2026-07-10

Tester: Sera Auvinen (90000014, qatest/fleet), L1 Spacelane Patrol agent
Aksalon Mihane (3016942) at Nomaa (60004231, system 30000131).
Tool: tools/simfleet/mission_courier_qa.py.

## Verdict: courier missions WORK end-to-end at the data level

First clean-state run generated a complete, valid courier mission:
- `DoAction(None)` opens the agent conversation (agentSays + dialog
  buttons, EVE_Agent.h: RequestMission=2 Accept=3 Complete=6 Decline=9
  Quit=11).
- `DoAction(2)` requests → returns a fresh offer ID.
- `GetMissionBriefingInfo` returns full keywords:
  `objectiveDestinationID` (dropoff station), `objectiveDestinationSystemID`,
  `rewardTypeID`/`rewardQuantity` (ISK reward), `objectiveTypeID` +
  `objectiveQuantity` (the courier package), mission title/image IDs.
  Example run: dropoff 60003085, reward 25,000 ISK, package typeID 16044 x20.
- `DoAction(3)` accepts → the courier **package is staged into the
  pilot's station hangar** (verified: typeID 16044 x20 appeared), and an
  `agtOffers` row is persisted (offerID, agentID, stateID, destinationID,
  courierTypeID, courierAmount) — MissionDB.cpp:47.

So the loader, offer generation, briefing, accept, package delivery, and
DB persistence all function.  The 38 courier data sets the server loads
at boot are live.

## Findings

### MISSION-4: GetMissionObjectiveInfo returns None
After accept, `GetMissionObjectiveInfo` returns `None` rather than an
objective list.  Not fatal — the courier destination and package are
fully described in the briefing keywords, which is where the client reads
them for couriers — but any consumer expecting the objective structure
gets nothing.  Confirm the Crucible client doesn't need it for couriers;
if it does, this is a client-facing gap.

### MISSION-5: an active mission blocks new briefings
Once a mission is accepted, re-opening the agent offers only
`ViewMission` (button 1) at the top dialog — not Quit (11).  Requesting a
new mission (DoAction 2) then returns an offer ID, but
`GetMissionBriefingInfo` returns `None` because the active mission is
still bound.  A pilot (or bot) cannot cleanly abandon via the top dialog;
the ViewMission(1) path must lead to a Quit/complete action.  The probe
now attempts a Quit-first but the button isn't offered at that level —
needs the ViewMission sub-dialog walked.

### MISSION-6: accepted missions are server-cached (DB edits don't stick)
Deleting the `agtOffers` row while the server is running does not clear
the mission — the mission manager holds it in memory and re-persists it.
Clearing a stuck mission requires a server restart or driving it to
completion/quit over the protocol.  (Same online-cache pattern as wallet
and item edits.)

## Next step (blocked on restart)
The full haul→deliver→complete leg needs Sera's stuck offer 5 cleared.
After the concurrent component-QA run finishes, restart the server
(offline), delete Sera's agtOffers rows, and re-run mission_courier_qa.py
for a clean request→accept→haul→deliver→complete with wallet-reward
verification.  Same-system couriers (dropoff in the home system) exercise
the station-to-station warp; cross-system couriers exercise travel.py.
