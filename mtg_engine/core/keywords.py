"""Keyword abilities system for MTG cards.

Handles all evergreen keywords and provides the framework for
deciduous and set-specific keywords.
"""

from __future__ import annotations

from enum import Enum, auto


class Keyword(Enum):
    """All supported keyword abilities."""

    # --- Evergreen (always in Standard) ---
    FLYING = auto()
    REACH = auto()
    FIRST_STRIKE = auto()
    DOUBLE_STRIKE = auto()
    DEATHTOUCH = auto()
    TRAMPLE = auto()
    LIFELINK = auto()
    VIGILANCE = auto()
    HASTE = auto()
    HEXPROOF = auto()
    MENACE = auto()
    DEFENDER = auto()
    FLASH = auto()
    INDESTRUCTIBLE = auto()
    WARD = auto()
    PROTECTION = auto()

    # --- Deciduous (frequent, not every set) ---
    PROWESS = auto()
    CYCLING = auto()
    KICKER = auto()
    FLASHBACK = auto()
    EQUIP = auto()

    # --- Historic/Retired ---
    FEAR = auto()
    INTIMIDATE = auto()
    SHROUD = auto()
    SHADOW = auto()
    HORSEMANSHIP = auto()
    LANDWALK = auto()
    FLANKING = auto()


# Keywords that are pure evasion (affect blocking legality)
EVASION_KEYWORDS = {
    Keyword.FLYING,
    Keyword.MENACE,
    Keyword.FEAR,
    Keyword.INTIMIDATE,
    Keyword.SHADOW,
    Keyword.HORSEMANSHIP,
}

# Keywords that prevent attacking
ATTACK_PREVENTION_KEYWORDS = {
    Keyword.DEFENDER,
}

# Keywords that affect combat damage
COMBAT_DAMAGE_KEYWORDS = {
    Keyword.FIRST_STRIKE,
    Keyword.DOUBLE_STRIKE,
    Keyword.DEATHTOUCH,
    Keyword.TRAMPLE,
    Keyword.LIFELINK,
}

# Keywords that affect targeting
TARGETING_KEYWORDS = {
    Keyword.HEXPROOF,
    Keyword.SHROUD,
    Keyword.WARD,
    Keyword.PROTECTION,
}

# DSL name -> Keyword enum mapping
KEYWORD_MAP: dict[str, Keyword] = {
    "flying": Keyword.FLYING,
    "reach": Keyword.REACH,
    "first_strike": Keyword.FIRST_STRIKE,
    "double_strike": Keyword.DOUBLE_STRIKE,
    "deathtouch": Keyword.DEATHTOUCH,
    "trample": Keyword.TRAMPLE,
    "lifelink": Keyword.LIFELINK,
    "vigilance": Keyword.VIGILANCE,
    "haste": Keyword.HASTE,
    "hexproof": Keyword.HEXPROOF,
    "menace": Keyword.MENACE,
    "defender": Keyword.DEFENDER,
    "flash": Keyword.FLASH,
    "indestructible": Keyword.INDESTRUCTIBLE,
    "ward": Keyword.WARD,
    "protection": Keyword.PROTECTION,
    "prowess": Keyword.PROWESS,
    "cycling": Keyword.CYCLING,
    "kicker": Keyword.KICKER,
    "flashback": Keyword.FLASHBACK,
    "equip": Keyword.EQUIP,
    "fear": Keyword.FEAR,
    "intimidate": Keyword.INTIMIDATE,
    "shroud": Keyword.SHROUD,
    "shadow": Keyword.SHADOW,
    "horsemanship": Keyword.HORSEMANSHIP,
    "landwalk": Keyword.LANDWALK,
    "flanking": Keyword.FLANKING,
}


def can_block(attacker_keywords: set[Keyword], blocker_keywords: set[Keyword],
              attacker_colors: set | None = None,
              blocker_colors: set | None = None) -> bool:
    """Check if a creature with blocker_keywords can legally block an attacker.

    Does NOT handle menace (requires 2+ blockers) — that's checked at the
    declare-blockers level since it depends on block count, not per-pair.
    """
    from mtg_engine.core.enums import Color

    # Flying: only blocked by flying or reach
    if Keyword.FLYING in attacker_keywords:
        if Keyword.FLYING not in blocker_keywords and Keyword.REACH not in blocker_keywords:
            return False

    # Shadow: only blocked by shadow; shadow can only block shadow
    if Keyword.SHADOW in attacker_keywords:
        if Keyword.SHADOW not in blocker_keywords:
            return False
    elif Keyword.SHADOW in blocker_keywords:
        return False

    # Horsemanship: only blocked by horsemanship
    if Keyword.HORSEMANSHIP in attacker_keywords:
        if Keyword.HORSEMANSHIP not in blocker_keywords:
            return False

    # Fear: only blocked by artifact creatures or black creatures
    if Keyword.FEAR in attacker_keywords:
        is_artifact = False  # would need card type info
        is_black = blocker_colors and Color.BLACK in blocker_colors
        if not is_artifact and not is_black:
            return False

    # Intimidate: only blocked by artifact creatures or creatures sharing a color
    if Keyword.INTIMIDATE in attacker_keywords:
        is_artifact = False  # would need card type info
        shares_color = (
            attacker_colors and blocker_colors
            and bool(attacker_colors & blocker_colors)
        )
        if not is_artifact and not shares_color:
            return False

    return True


def has_summoning_sickness_immunity(keywords: set[Keyword]) -> bool:
    """Check if a creature ignores summoning sickness."""
    return Keyword.HASTE in keywords


def taps_when_attacking(keywords: set[Keyword]) -> bool:
    """Check if a creature taps when declared as attacker."""
    return Keyword.VIGILANCE not in keywords


def is_damage_lethal(damage: int, toughness: int, source_has_deathtouch: bool) -> bool:
    """Check if damage amount is lethal considering deathtouch."""
    if source_has_deathtouch and damage > 0:
        return True
    return damage >= toughness


def can_be_targeted_by_opponent(keywords: set[Keyword]) -> bool:
    """Check if a permanent can be targeted by an opponent's spell/ability."""
    if Keyword.HEXPROOF in keywords or Keyword.SHROUD in keywords:
        return False
    return True


def can_be_targeted_by_controller(keywords: set[Keyword]) -> bool:
    """Check if a permanent can be targeted by its controller."""
    if Keyword.SHROUD in keywords:
        return False
    return True


def can_be_destroyed(keywords: set[Keyword]) -> bool:
    """Check if a permanent can be destroyed."""
    return Keyword.INDESTRUCTIBLE not in keywords
