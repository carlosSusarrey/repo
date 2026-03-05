"""Card definitions and card instances on the battlefield."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from mtg_engine.core.enums import CardType, Color, SuperType, Zone
from mtg_engine.core.mana import ManaCost


@dataclass
class Card:
    """A card definition (template, not an instance in a game)."""

    name: str
    card_type: CardType
    cost: ManaCost = field(default_factory=lambda: ManaCost())
    supertypes: list[SuperType] = field(default_factory=list)
    subtypes: list[str] = field(default_factory=list)
    power: int | None = None
    toughness: int | None = None
    loyalty: int | None = None
    rules_text: str = ""
    effects: list[dict[str, Any]] = field(default_factory=list)

    @property
    def colors(self) -> set[Color]:
        return self.cost.colors

    @property
    def is_creature(self) -> bool:
        return self.card_type == CardType.CREATURE

    @property
    def is_land(self) -> bool:
        return self.card_type == CardType.LAND

    @property
    def is_instant(self) -> bool:
        return self.card_type == CardType.INSTANT

    @property
    def is_sorcery(self) -> bool:
        return self.card_type == CardType.SORCERY

    def __str__(self) -> str:
        parts = [self.name, f"({self.cost})"]
        if self.is_creature:
            parts.append(f"{self.power}/{self.toughness}")
        return " ".join(parts)


@dataclass
class CardInstance:
    """A specific instance of a card in a game (tracks state)."""

    card: Card
    instance_id: str = field(default_factory=lambda: str(uuid4())[:8])
    zone: Zone = Zone.LIBRARY
    owner_index: int = 0
    controller_index: int = 0
    tapped: bool = False
    summoning_sick: bool = False
    damage_marked: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    attached_to: str | None = None
    attachments: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.card.name

    @property
    def current_power(self) -> int | None:
        """Power with modifications applied."""
        if self.card.power is None:
            return None
        base = self.card.power
        base += self.counters.get("+1/+1", 0)
        base -= self.counters.get("-1/-1", 0)
        return base

    @property
    def current_toughness(self) -> int | None:
        """Toughness with modifications applied."""
        if self.card.toughness is None:
            return None
        base = self.card.toughness
        base += self.counters.get("+1/+1", 0)
        base -= self.counters.get("-1/-1", 0)
        return base

    @property
    def lethal_damage(self) -> bool:
        """Whether this creature has lethal damage marked."""
        if self.current_toughness is None:
            return False
        return self.damage_marked >= self.current_toughness

    def tap(self) -> None:
        self.tapped = True

    def untap(self) -> None:
        self.tapped = False

    def __str__(self) -> str:
        status = []
        if self.tapped:
            status.append("tapped")
        if self.damage_marked > 0:
            status.append(f"{self.damage_marked} dmg")
        suffix = f" [{', '.join(status)}]" if status else ""
        return f"{self.card}{suffix}"
