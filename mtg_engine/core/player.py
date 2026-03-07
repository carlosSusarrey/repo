"""Player state management."""

from __future__ import annotations

from dataclasses import dataclass, field

from mtg_engine.core.card import CardInstance
from mtg_engine.core.enums import Zone
from mtg_engine.core.mana import ManaPool


@dataclass
class Player:
    """Represents a player in the game."""

    name: str
    life: int = 20
    mana_pool: ManaPool = field(default_factory=ManaPool)
    has_drawn_for_turn: bool = False
    land_plays_remaining: int = 1
    poison_counters: int = 0
    lost: bool = False
    won: bool = False

    def lose_life(self, amount: int) -> int:
        """Lose life. Returns amount lost."""
        self.life -= amount
        if self.life <= 0:
            self.lost = True
        return amount

    def gain_life(self, amount: int) -> int:
        """Gain life. Returns amount gained."""
        self.life += amount
        return amount

    def deal_damage(self, amount: int) -> int:
        """Deal damage to this player (loss of life from damage)."""
        return self.lose_life(amount)

    def reset_for_turn(self) -> None:
        """Reset per-turn state at the beginning of a turn."""
        self.has_drawn_for_turn = False
        self.land_plays_remaining = 1
