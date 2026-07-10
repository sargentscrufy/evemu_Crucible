"""
Crucible killboard-style tank fittings for PvP tank trials.

typeIDs resolved against the live static data. Slot flags:
  hi 27-34, med 19-26, low 11-18.  Charges go to cargo flag 5.
Skills are granted via skill_closure over all fitted types.
"""

# module typeIDs (resolved from invTypes)
CIV_RAILGUN   = 3638   # Civilian Gatling Railgun (ammoless, attacker)
RAILGUN_150   = 565
ANTIMATTER_S  = 222

SSE           = 377    # Small Shield Extender I
SHIELD_BOOST  = 399    # Small Shield Booster I
AMP_KIN       = 2545   # Kinetic Deflection Amplifier I (shield)
AMP_THERM     = 2537   # Heat Dissipation Amplifier I (shield)

PLATE_200     = 11295  # 200mm Reinforced Steel Plates I
PLATE_400     = 11297  # 400mm Reinforced Steel Plates I
ANP           = 1304   # Adaptive Nano Plating I (armor omni resist)
DC            = 2046   # Damage Control I (shield+armor+hull resist)
ARM_HARD_KIN  = 11305  # Armor Kinetic Hardener I
ARM_HARD_TH   = 11277  # Armor Thermic Hardener I
SMALL_ARM_REP = 523    # Small Armor Repairer I

# hull typeIDs
MERLIN    = 603
RIFTER    = 587
INCURSUS  = 594
PUNISHER  = 597
CORMORANT = 16238

# ---- fit format: (hull, {"hi":[...], "med":[...], "low":[...]}) ----
# defenders: tank variety across shield/armor/active/resist/buffer
DEFENDER_FITS = {
    "merlin_shield_buffer":   (MERLIN, {"med": [SSE, SSE]}),
    "merlin_shield_resist":   (MERLIN, {"med": [SSE, AMP_KIN, AMP_THERM]}),
    "merlin_shield_active":   (MERLIN, {"med": [SHIELD_BOOST]}),
    "merlin_untanked":        (MERLIN, {}),
    "rifter_armor_buffer":    (RIFTER, {"low": [PLATE_200, DC]}),
    "rifter_armor_resist":    (RIFTER, {"low": [PLATE_200, ANP, DC]}),
    "incursus_armor_active":  (INCURSUS, {"low": [SMALL_ARM_REP, DC]}),
    "punisher_heavy_armor":   (PUNISHER, {"low": [PLATE_400, ARM_HARD_KIN, ARM_HARD_TH]}),
    "cormorant_shield_buffer":(CORMORANT, {"med": [SSE, SSE]}),
    "merlin_dual_light":      (MERLIN, {"med": [SSE], "low": [PLATE_200]}),
}

# attacker: fixed civilian-gun Cormorant (ammoless, ~constant DPS)
ATTACKER_FIT = (CORMORANT, {"hi": [CIV_RAILGUN] * 7})


def all_fitted_types(fit):
    hull, slots = fit
    tids = [hull]
    for rack in slots.values():
        tids.extend(rack)
    return tids
