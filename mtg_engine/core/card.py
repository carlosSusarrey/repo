"""Card definitions and card instances on the battlefield."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from mtg_engine.core.enums import CardType, Color, SuperType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


@dataclass
class Card:
    """A card definition (template, not an instance in a game)."""

    name: str
    card_type: CardType = CardType.CREATURE  # Primary type (backwards compat)
    card_types: list[CardType] = field(default_factory=list)  # All types (e.g., [ARTIFACT, CREATURE])
    cost: ManaCost = field(default_factory=lambda: ManaCost())
    supertypes: list[SuperType] = field(default_factory=list)
    subtypes: list[str] = field(default_factory=list)
    power: int | None = None
    toughness: int | None = None
    loyalty: int | None = None
    rules_text: str = ""
    effects: list[dict[str, Any]] = field(default_factory=list)
    keywords: set[Keyword] = field(default_factory=set)
    triggered_abilities: list[dict[str, Any]] = field(default_factory=list)
    activated_abilities: list[dict[str, Any]] = field(default_factory=list)
    keyword_params: dict[Keyword, Any] = field(default_factory=dict)
    replacement_effects: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure card_types list is synced with card_type."""
        if not self.card_types:
            self.card_types = [self.card_type]
        elif self.card_type not in self.card_types:
            self.card_type = self.card_types[0]

    def has_type(self, card_type: CardType) -> bool:
        """Check if this card has a given type (supports multi-type)."""
        return card_type in self.card_types

    @property
    def colors(self) -> set[Color]:
        return self.cost.colors

    @property
    def is_creature(self) -> bool:
        return CardType.CREATURE in self.card_types

    @property
    def is_land(self) -> bool:
        return CardType.LAND in self.card_types

    @property
    def is_instant(self) -> bool:
        return CardType.INSTANT in self.card_types

    @property
    def is_sorcery(self) -> bool:
        return CardType.SORCERY in self.card_types

    @property
    def is_artifact(self) -> bool:
        return CardType.ARTIFACT in self.card_types

    @property
    def is_enchantment(self) -> bool:
        return CardType.ENCHANTMENT in self.card_types

    @property
    def is_battle(self) -> bool:
        return CardType.BATTLE in self.card_types

    def has_keyword(self, keyword: Keyword) -> bool:
        return keyword in self.keywords

    def __str__(self) -> str:
        parts = [self.name, f"({self.cost})"]
        if self.is_creature:
            parts.append(f"{self.power}/{self.toughness}")
        return " ".join(parts)


@dataclass
class CardInstance:
    """A specific instance of a card in a game (tracks state).

    When on the stack, this object *is* the stack entry — it satisfies the
    ``Stackable`` protocol via the ``source_id``, ``card_name``, ``effects``,
    and ``targets`` properties.
    """

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
    # Runtime keyword modifications (gained/lost this turn etc.)
    granted_keywords: set[Keyword] = field(default_factory=set)
    removed_keywords: set[Keyword] = field(default_factory=set)
    # Temporary P/T modifications (until end of turn)
    temp_power_mod: int = 0
    temp_toughness_mod: int = 0
    # Token tracking
    is_token: bool = False
    # Stack state — populated when casting, cleared on resolution
    _stack_effects: list[dict[str, Any]] = field(default_factory=list)
    _stack_targets: list[str] = field(default_factory=list)

    # -- Stackable protocol properties --

    @property
    def source_id(self) -> str:
        return self.instance_id

    @property
    def card_name(self) -> str:
        return self.card.name

    @property
    def effects(self) -> list[dict[str, Any]]:
        return self._stack_effects

    @effects.setter
    def effects(self, value: list[dict[str, Any]]) -> None:
        self._stack_effects = value

    @property
    def targets(self) -> list[str]:
        return self._stack_targets

    @targets.setter
    def targets(self, value: list[str]) -> None:
        self._stack_targets = value

    @property
    def name(self) -> str:
        return self.card.name

    @property
    def keywords(self) -> set[Keyword]:
        """Current keywords (base + granted - removed)."""
        return (self.card.keywords | self.granted_keywords) - self.removed_keywords

    def has_keyword(self, keyword: Keyword) -> bool:
        return keyword in self.keywords

    @property
    def current_power(self) -> int | None:
        """Power with modifications applied."""
        if self.card.power is None:
            return None
        base = self.card.power
        base += self.counters.get("+1/+1", 0)
        base -= self.counters.get("-1/-1", 0)
        base += self.temp_power_mod
        return base

    @property
    def current_toughness(self) -> int | None:
        """Toughness with modifications applied."""
        if self.card.toughness is None:
            return None
        base = self.card.toughness
        base += self.counters.get("+1/+1", 0)
        base -= self.counters.get("-1/-1", 0)
        base += self.temp_toughness_mod
        return base

    @property
    def lethal_damage(self) -> bool:
        """Whether this creature has lethal damage marked."""
        if self.current_toughness is None:
            return False
        return self.damage_marked >= self.current_toughness

    def can_attack(self) -> bool:
        """Check if this creature can be declared as an attacker."""
        if not self.card.is_creature:
            return False
        if self.zone != Zone.BATTLEFIELD:
            return False
        if self.tapped:
            return False
        if self.has_keyword(Keyword.DEFENDER):
            return False
        if self.summoning_sick and not self.has_keyword(Keyword.HASTE):
            return False
        return True

    def can_block(self) -> bool:
        """Check if this creature can be declared as a blocker."""
        if not self.card.is_creature:
            return False
        if self.zone != Zone.BATTLEFIELD:
            return False
        if self.tapped:
            return False
        return True

    def tap(self) -> None:
        self.tapped = True

    def untap(self) -> None:
        self.tapped = False

    def clear_stack_state(self) -> None:
        """Clear stack-related state after resolution or leaving the stack."""
        self._stack_effects = []
        self._stack_targets = []

    def clear_end_of_turn(self) -> None:
        """Clear temporary effects at end of turn."""
        self.temp_power_mod = 0
        self.temp_toughness_mod = 0
        self.granted_keywords.clear()
        self.removed_keywords.clear()

    def __str__(self) -> str:
        status = []
        if self.tapped:
            status.append("tapped")
        if self.damage_marked > 0:
            status.append(f"{self.damage_marked} dmg")
        kw_strs = [kw.name.lower() for kw in self.keywords]
        if kw_strs:
            status.append(", ".join(kw_strs))
        suffix = f" [{', '.join(status)}]" if status else ""
        return f"{self.card}{suffix}"
