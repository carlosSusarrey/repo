"""Game enumerations for MTG concepts."""

from enum import Enum, auto


class Color(Enum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"
    COLORLESS = "C"


class CardType(Enum):
    CREATURE = auto()
    INSTANT = auto()
    SORCERY = auto()
    ENCHANTMENT = auto()
    ARTIFACT = auto()
    PLANESWALKER = auto()
    LAND = auto()
    BATTLE = auto()


class SuperType(Enum):
    LEGENDARY = auto()
    BASIC = auto()
    SNOW = auto()


class Phase(Enum):
    BEGINNING = auto()
    PRECOMBAT_MAIN = auto()
    COMBAT = auto()
    POSTCOMBAT_MAIN = auto()
    ENDING = auto()


class Step(Enum):
    # Beginning phase
    UNTAP = auto()
    UPKEEP = auto()
    DRAW = auto()
    # Main phase (no steps, but we use this as a marker)
    MAIN = auto()
    # Combat phase
    BEGINNING_OF_COMBAT = auto()
    DECLARE_ATTACKERS = auto()
    DECLARE_BLOCKERS = auto()
    COMBAT_DAMAGE = auto()
    END_OF_COMBAT = auto()
    # Ending phase
    END = auto()
    CLEANUP = auto()


class Zone(Enum):
    LIBRARY = auto()
    HAND = auto()
    BATTLEFIELD = auto()
    GRAVEYARD = auto()
    STACK = auto()
    EXILE = auto()
    COMMAND = auto()
