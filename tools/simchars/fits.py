"""
Archetype fit templates for sim characters.

Templates reference type NAMES (resolved against invTypes at provision
time) so they survive static-data differences. The selector validates a
fit against the ship's real slot layout (dogma attrs 12/13/14) and the
local market before committing, and degrades gracefully: modules that
don't fit or can't be bought are dropped with a note, not a failure.

Slot flags (EVE inventory flags):
  low 11-18, mid 19-26, high 27-34
"""

from dataclasses import dataclass, field

FLAG_LO_FIRST, FLAG_MID_FIRST, FLAG_HI_FIRST = 11, 19, 27
FLAG_CARGO = 5
FLAG_HANGAR = 4


@dataclass
class FitTemplate:
    archetype: str          # 'hauler', 'miner', 'responder', ...
    name: str
    ship: str               # type name
    lows: list = field(default_factory=list)    # type names, in order
    mids: list = field(default_factory=list)
    highs: list = field(default_factory=list)
    cargo: list = field(default_factory=list)   # (type name, qty)
    notes: str = ""


# ---------------------------------------------------------------- fits

FITS = [
    FitTemplate(
        archetype="hauler",
        name="badger-runner",
        ship="Badger",
        lows=["Expanded Cargohold I", "Expanded Cargohold I"],
        mids=["1MN Afterburner I", "Small Shield Extender I"],
        highs=[],
        notes="Cheap starter hauler; cargo-fit, shield buffer, AB.",
    ),
    FitTemplate(
        archetype="hauler",
        name="badger2-runner",
        ship="Badger Mark II",
        lows=["Expanded Cargohold I", "Expanded Cargohold I",
              "Expanded Cargohold I"],
        mids=["1MN Afterburner I", "Small Shield Extender I"],
        highs=[],
        notes="Bigger wallet variant; selector prefers it when affordable.",
    ),
    FitTemplate(
        archetype="miner",
        name="bantam-digger",
        ship="Bantam",
        lows=["Expanded Cargohold I"],
        mids=["Small Shield Extender I"],
        highs=["Miner I", "Miner I"],
        notes="Starter belt miner.",
    ),
    FitTemplate(
        archetype="responder",
        name="patrol-merlin",
        ship="Merlin",
        lows=["Expanded Cargohold I"],
        mids=["Small Shield Extender I", "1MN Afterburner I"],
        highs=["125mm Gatling AutoCannon I", "125mm Gatling AutoCannon I"],
        notes="Placeholder 'faction police / CONCORD responder' hull until "
              "the Director gets proper response doctrine; see README.",
    ),
]


def templates_for(archetype):
    return [f for f in FITS if f.archetype == archetype]


def slot_flags(template, low_slots, mid_slots, hi_slots):
    """Yield (type_name, flag) honoring the ship's real slot layout.

    Modules beyond the ship's slot count are dropped (reported by caller).
    """
    plan, dropped = [], []
    for names, first, count in (
            (template.lows, FLAG_LO_FIRST, low_slots),
            (template.mids, FLAG_MID_FIRST, mid_slots),
            (template.highs, FLAG_HI_FIRST, hi_slots)):
        for i, type_name in enumerate(names):
            if i < count:
                plan.append((type_name, first + i))
            else:
                dropped.append(type_name)
    return plan, dropped
