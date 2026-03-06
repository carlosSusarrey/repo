"""7-Layer continuous effects system.

CR 613: The layer system determines how continuous effects interact.
Effects are applied in order from layer 1 to layer 7, with timestamps
breaking ties within the same layer.

Layer 1: Copy effects
Layer 2: Control-changing effects
Layer 3: Text-changing effects
Layer 4: Type-changing effects
Layer 5: Color-changing effects
Layer 6: Ability-adding/removing effects
Layer 7: Power/toughness effects
  7a: Characteristic-defining abilities (e.g., Tarmogoyf)
  7b: Setting P/T to specific values
  7c: Modifications from +1/+1 and -1/-1 counters
  7d: Effects that modify P/T (e.g., +2/+2 from equipment)
  7e: Effects that switch P/T
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.enums import CardType, Color, Zone
from mtg_engine.core.keywords import Keyword


class Layer(Enum):
    """The 7 layers of continuous effect application."""
    COPY = 1
    CONTROL = 2
    TEXT = 3
    TYPE = 4
    COLOR = 5
    ABILITY = 6
    POWER_TOUGHNESS = 7


class PTSublayer(Enum):
    """Sublayers within Layer 7 (Power/Toughness)."""
    CDA = auto()        # 7a: Characteristic-defining abilities
    SET = auto()         # 7b: Set P/T to specific values
    COUNTERS = auto()    # 7c: +1/+1 and -1/-1 counters
    MODIFY = auto()      # 7d: Modifications (+N/+N effects)
    SWITCH = auto()      # 7e: Switch P/T


@dataclass
class ContinuousEffect:
    """A continuous effect that modifies game objects.

    Continuous effects come from static abilities on permanents,
    spells that have resolved, or the rules of the game.
    """
    source_id: str
    layer: Layer
    pt_sublayer: PTSublayer | None = None
    timestamp: int = 0

    # What this effect does (varies by layer)
    # Layer 2: control change
    new_controller: int | None = None
    # Layer 3: text changes
    text_replacements: dict[str, str] = field(default_factory=dict)
    # Layer 4: type changes
    add_types: list[CardType] = field(default_factory=list)
    remove_types: list[CardType] = field(default_factory=list)
    add_subtypes: list[str] = field(default_factory=list)
    remove_subtypes: list[str] = field(default_factory=list)
    # Layer 5: color changes
    add_colors: set[Color] = field(default_factory=set)
    remove_colors: set[Color] = field(default_factory=set)
    set_colors: set[Color] | None = None
    # Layer 6: ability changes
    add_keywords: set[Keyword] = field(default_factory=set)
    remove_keywords: set[Keyword] = field(default_factory=set)
    # Layer 7: P/T changes
    set_power: int | None = None
    set_toughness: int | None = None
    power_mod: int = 0
    toughness_mod: int = 0
    switch_pt: bool = False

    # Which objects this effect applies to
    affected_ids: list[str] = field(default_factory=list)
    # Or a filter function for effects that apply broadly
    affect_filter: str = ""  # e.g., "all_creatures", "your_creatures"

    # Duration
    duration: str = "permanent"  # "permanent", "end_of_turn", "until_leaves"


class ContinuousEffectManager:
    """Manages all active continuous effects and applies them in layer order."""

    def __init__(self) -> None:
        self._effects: list[ContinuousEffect] = []
        self._timestamp: int = 0

    def add_effect(self, effect: ContinuousEffect) -> None:
        """Add a new continuous effect with a timestamp."""
        self._timestamp += 1
        effect.timestamp = self._timestamp
        self._effects.append(effect)

    def remove_effects_from(self, source_id: str) -> None:
        """Remove all effects from a given source (e.g., when a permanent leaves)."""
        self._effects = [e for e in self._effects if e.source_id != source_id]

    def remove_end_of_turn_effects(self) -> None:
        """Remove all end-of-turn effects during cleanup."""
        self._effects = [e for e in self._effects if e.duration != "end_of_turn"]

    @property
    def effects(self) -> list[ContinuousEffect]:
        return list(self._effects)

    def apply_all(
        self,
        cards: list[CardInstance],
        card_lookup: dict[str, CardInstance],
    ) -> None:
        """Apply all continuous effects in layer order.

        This recalculates the game state from base characteristics,
        applying effects in the correct order.
        """
        # Sort effects by layer, then sublayer, then timestamp
        sorted_effects = sorted(
            self._effects,
            key=lambda e: (
                e.layer.value,
                e.pt_sublayer.value if e.pt_sublayer else 0,
                e.timestamp,
            ),
        )

        for effect in sorted_effects:
            affected = self._get_affected_cards(effect, cards, card_lookup)
            self._apply_single_effect(effect, affected)

    def _get_affected_cards(
        self,
        effect: ContinuousEffect,
        cards: list[CardInstance],
        card_lookup: dict[str, CardInstance],
    ) -> list[CardInstance]:
        """Determine which cards an effect applies to."""
        if effect.affected_ids:
            return [
                card_lookup[cid]
                for cid in effect.affected_ids
                if cid in card_lookup
            ]

        if effect.affect_filter == "all_creatures":
            return [c for c in cards if c.card.is_creature and c.zone == Zone.BATTLEFIELD]
        if effect.affect_filter == "your_creatures":
            source = card_lookup.get(effect.source_id)
            if source:
                return [
                    c for c in cards
                    if c.card.is_creature
                    and c.zone == Zone.BATTLEFIELD
                    and c.controller_index == source.controller_index
                ]
        if effect.affect_filter == "opponent_creatures":
            source = card_lookup.get(effect.source_id)
            if source:
                return [
                    c for c in cards
                    if c.card.is_creature
                    and c.zone == Zone.BATTLEFIELD
                    and c.controller_index != source.controller_index
                ]
        if effect.affect_filter == "all_permanents":
            return [c for c in cards if c.zone == Zone.BATTLEFIELD]
        if effect.affect_filter == "your_permanents":
            source = card_lookup.get(effect.source_id)
            if source:
                return [
                    c for c in cards
                    if c.zone == Zone.BATTLEFIELD
                    and c.controller_index == source.controller_index
                ]

        return []

    def _apply_single_effect(
        self,
        effect: ContinuousEffect,
        affected: list[CardInstance],
    ) -> None:
        """Apply a single continuous effect to the affected cards."""
        for card in affected:
            match effect.layer:
                case Layer.CONTROL:
                    if effect.new_controller is not None:
                        card.controller_index = effect.new_controller

                case Layer.TEXT:
                    # Text-changing effects modify rules text
                    if effect.text_replacements:
                        new_text = card.card.rules_text
                        for old, new in effect.text_replacements.items():
                            new_text = new_text.replace(old, new)
                        card.card.rules_text = new_text

                case Layer.TYPE:
                    # Type-changing effects add/remove types and subtypes
                    for t in effect.add_types:
                        if t not in [card.card.card_type]:
                            # For multi-type support, we'd need a list
                            # For now, change the primary type
                            card.card.card_type = t
                    for st in effect.add_subtypes:
                        if st not in card.card.subtypes:
                            card.card.subtypes.append(st)
                    for st in effect.remove_subtypes:
                        if st in card.card.subtypes:
                            card.card.subtypes.remove(st)

                case Layer.COLOR:
                    # Color-changing effects
                    if effect.set_colors is not None:
                        # Override all colors
                        card._override_colors = set(effect.set_colors)  # type: ignore[attr-defined]
                    else:
                        override = getattr(card, '_override_colors', None)
                        if override is None:
                            override = set(card.card.colors)
                        for c in effect.add_colors:
                            override.add(c)
                        for c in effect.remove_colors:
                            override.discard(c)
                        card._override_colors = override  # type: ignore[attr-defined]

                case Layer.ABILITY:
                    for kw in effect.add_keywords:
                        card.granted_keywords.add(kw)
                    for kw in effect.remove_keywords:
                        card.removed_keywords.add(kw)

                case Layer.POWER_TOUGHNESS:
                    match effect.pt_sublayer:
                        case PTSublayer.SET:
                            if effect.set_power is not None:
                                # Reset to base then set
                                card.temp_power_mod = effect.set_power - (card.card.power or 0)
                            if effect.set_toughness is not None:
                                card.temp_toughness_mod = effect.set_toughness - (card.card.toughness or 0)

                        case PTSublayer.MODIFY:
                            card.temp_power_mod += effect.power_mod
                            card.temp_toughness_mod += effect.toughness_mod

                        case PTSublayer.SWITCH:
                            if effect.switch_pt:
                                current_p = card.current_power or 0
                                current_t = card.current_toughness or 0
                                # Swap by adjusting mods
                                base_p = card.card.power or 0
                                base_t = card.card.toughness or 0
                                card.temp_power_mod = current_t - base_p
                                card.temp_toughness_mod = current_p - base_t


def create_pump_effect(
    source_id: str,
    target_id: str,
    power: int,
    toughness: int,
    duration: str = "end_of_turn",
) -> ContinuousEffect:
    """Create a pump effect (e.g., Giant Growth gives +3/+3)."""
    return ContinuousEffect(
        source_id=source_id,
        layer=Layer.POWER_TOUGHNESS,
        pt_sublayer=PTSublayer.MODIFY,
        affected_ids=[target_id],
        power_mod=power,
        toughness_mod=toughness,
        duration=duration,
    )


def create_keyword_grant_effect(
    source_id: str,
    target_id: str,
    keywords: set[Keyword],
    duration: str = "end_of_turn",
) -> ContinuousEffect:
    """Create an effect that grants keywords (e.g., equipment giving flying)."""
    return ContinuousEffect(
        source_id=source_id,
        layer=Layer.ABILITY,
        affected_ids=[target_id],
        add_keywords=keywords,
        duration=duration,
    )


def create_anthem_effect(
    source_id: str,
    power: int,
    toughness: int,
    affect_filter: str = "your_creatures",
) -> ContinuousEffect:
    """Create an anthem effect (e.g., Glorious Anthem gives +1/+1 to your creatures)."""
    return ContinuousEffect(
        source_id=source_id,
        layer=Layer.POWER_TOUGHNESS,
        pt_sublayer=PTSublayer.MODIFY,
        affect_filter=affect_filter,
        power_mod=power,
        toughness_mod=toughness,
        duration="until_leaves",
    )


def create_control_change_effect(
    source_id: str,
    target_id: str,
    new_controller: int,
    duration: str = "permanent",
) -> ContinuousEffect:
    """Create a control-changing effect (e.g., Mind Control)."""
    return ContinuousEffect(
        source_id=source_id,
        layer=Layer.CONTROL,
        affected_ids=[target_id],
        new_controller=new_controller,
        duration=duration,
    )


def create_type_change_effect(
    source_id: str,
    target_id: str,
    add_types: list[CardType] | None = None,
    remove_types: list[CardType] | None = None,
    add_subtypes: list[str] | None = None,
    remove_subtypes: list[str] | None = None,
    duration: str = "permanent",
) -> ContinuousEffect:
    """Create a type-changing effect (e.g., turning an artifact into a creature)."""
    return ContinuousEffect(
        source_id=source_id,
        layer=Layer.TYPE,
        affected_ids=[target_id],
        add_types=add_types or [],
        remove_types=remove_types or [],
        add_subtypes=add_subtypes or [],
        remove_subtypes=remove_subtypes or [],
        duration=duration,
    )


def create_color_change_effect(
    source_id: str,
    target_id: str,
    set_colors: set[Color] | None = None,
    add_colors: set[Color] | None = None,
    remove_colors: set[Color] | None = None,
    duration: str = "permanent",
) -> ContinuousEffect:
    """Create a color-changing effect (e.g., painting something blue)."""
    return ContinuousEffect(
        source_id=source_id,
        layer=Layer.COLOR,
        affected_ids=[target_id],
        set_colors=set_colors,
        add_colors=add_colors or set(),
        remove_colors=remove_colors or set(),
        duration=duration,
    )


def create_text_change_effect(
    source_id: str,
    target_id: str,
    replacements: dict[str, str],
    duration: str = "permanent",
) -> ContinuousEffect:
    """Create a text-changing effect (e.g., changing 'swamp' to 'island')."""
    return ContinuousEffect(
        source_id=source_id,
        layer=Layer.TEXT,
        affected_ids=[target_id],
        text_replacements=replacements,
        duration=duration,
    )
