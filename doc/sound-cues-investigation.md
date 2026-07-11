# Sound & Music Cue Investigation (2026-07-11)

Deep dive into how the server drives client audio, and the root cause of
MUSIC-1 ("combat music never switches from ambient to combat").

## How EVE audio is driven

EVE's client owns all audio. The server never sends "play sound X" or "play
combat music"; it sends **combat state and effect events**, and the client's
audio system decides what to play. So every cue below is really "does the
server emit the event the client keys off?"

## Cue-by-cue map

| Cue | Server driver | Status |
|---|---|---|
| **Turret / module fire** (beam + sound) | `OnSpecialFX` (`DestinyManager::SendSpecialEffect`, guid `effects.Laser` etc.) | **OK** — EFFECT-1 + GUN-1 (repeat=1) validated |
| **Missile launch / flight / impact** | `OnSpecialFX` + missile projectile | **OK** (fires; impact applies damage) |
| **Target-lock beeps** | `OnTarget` events — `add` (you locked), `otheradd` (locked by someone), `lost`/`otherlost`; sent via `OnMultiEvent`/destiny queue (`TargetManager.cpp:400-461`) | **OK** — all modes emitted |
| **Incoming-fire / hit feedback** | `OnDamageStateChange` (`SystemEntity::SendDamageStateChanged`) + damage | **OK** — validated live in the tank suite |
| **Ship explosion / death** | structure→0 in `OnDamageStateChange` + entity/ball removal (`SystemEntity::Killed`) | **OK** — client renders explosion+sound; bots explode/pod repeatedly |
| **Notify/UI sounds** | notify messages carry `urlAudio` (`wise:/msg_*_play`) | **OK** — sent with the message |
| **Dungeon/mission music** | slim item `dunMusicUrl` (`SystemEntity.cpp:447`, e.g. `res:/Sound/Music/Ambient031combat.ogg`) | present, **dungeon-scoped only** (has `dunRoomName`, `dunKeyTypeID`) |
| **General combat music** | *(no server trigger — client heuristic)* | **see MUSIC-1** |

## MUSIC-1 root cause

**There is no server-side "combat music" trigger, and there shouldn't be** —
general combat music is a pure client-side heuristic in the Crucible client,
driven by the combat state the server already communicates:

- weapon FX events (`OnSpecialFX`) — emitted on every shot,
- being targeted (`OnTarget` mode `otheradd`) — emitted,
- taking damage (`OnDamageStateChange` + damage) — emitted.

All three are implemented and validated. So in a **real client**, combat music
should switch when combat starts. MUSIC-1 was flagged "BROKEN" only because the
headless test bots have **no audio subsystem** — the cue is literally
unobservable to them, not proven absent. It is **not a discrete server bug**
with a code fix; there is nothing to "turn on" server-side.

**Verification path:** MUSIC-1 can only be confirmed/denied with a real game
client on grid during combat. Recommend closing it as "client-side; inputs
supplied" and verifying opportunistically when a human client connects.

## The one concrete adjacent gap

`Client::GetAggressors()` (`Client.cpp:1419`) is a **stub** — returns
`nullptr`/None. It feeds `ss.aggressors` in the session snapshot
(`SystemManager.cpp:1430`), i.e. the **undock/jump-with-aggression safety
system** (can't-dock timers, aggression flags), NOT music. Related to the
CrimeWatch stub noted in the combat validation. Implementing it belongs with
the **consequence-layer sprint** (crime/aggression/CONCORD), not with audio.

## Verdict

The sound-cue pipeline is **functionally complete on the server side**: every
event the client needs to drive weapon sounds, targeting beeps, hit/explosion
audio, and the combat-music heuristic is emitted. No audio-specific server fix
is warranted. MUSIC-1 should be reclassified from "BROKEN" to
"client-side / verify with a real client." The only real gap uncovered
(`GetAggressors`) is an aggression/safety feature for the consequence sprint.
