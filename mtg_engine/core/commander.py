"""Commander format rules.

CR 903: Commander is a multiplayer format with specific rules:
- Each player has a commander in the command zone
- Color identity restricts deck building
- Commander tax: +{2} for each time cast from command zone
- Commander damage: 21+ combat damage from a single commander = loss
- Starting life: 40
- Deck size: exactly 100 (including commander)
- Singleton: only 1 copy of each card (except basic lands)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, SuperType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


COMMANDER_STARTING_LIFE = 40
COMMANDER_DAMAGE_THRESHOLD = 21
COMMANDER_DECK_SIZE = 100
COMMANDER_TAX_INCREMENT = ManaCost(generic=2)


@dataclass
class CommanderState:
    """Tracks commander-specific state for a player."""
    commander_id: str = ""
    partner_id: str | None = None  # For partner commanders
    times_cast: int = 0
    # Track combat damage from each opposing commander
    commander_damage_taken: dict[str, int] = field(default_factory=dict)


def get_color_identity(card: Card) -> set[Color]:
    """Get the color identity of a card (CR 903.4).

    Color identity includes:
    - Colors in the mana cost
    - Colors of any mana symbols in the rules text
    - Color indicator (if any)
    """
    identity = set(card.cost.colors)

    # Check rules text for mana symbols
    import re
    mana_symbols = re.findall(r"\{([WUBRG])\}", card.rules_text)
    color_map = {
        "W": Color.WHITE, "U": Color.BLUE, "B": Color.BLACK,
        "R": Color.RED, "G": Color.GREEN,
    }
    for sym in mana_symbols:
        if sym in color_map:
            identity.add(color_map[sym])

    # Check hybrid mana in cost
    for h in card.cost.hybrid:
        if h.color1 in color_map:
            identity.add(color_map[h.color1])
        if h.color2 in color_map:
            identity.add(color_map[h.color2])

    # Check phyrexian mana
    for p in card.cost.phyrexian:
        if p.color in color_map:
            identity.add(color_map[p.color])

    return identity


def is_legal_in_deck(card: Card, commander_identity: set[Color]) -> bool:
    """Check if a card is legal in a commander deck (CR 903.5c).

    A card's color identity must be a subset of the commander's.
    Basic lands are always allowed.
    """
    if SuperType.BASIC in card.supertypes and card.card_type == CardType.LAND:
        card_identity = get_color_identity(card)
        return card_identity.issubset(commander_identity)

    card_identity = get_color_identity(card)
    return card_identity.issubset(commander_identity)


def validate_commander(card: Card) -> bool:
    """Check if a card can be a commander (CR 903.3).

    Must be a legendary creature (or have 'can be your commander').
    """
    return (
        SuperType.LEGENDARY in card.supertypes
        and card.card_type == CardType.CREATURE
    )


def validate_deck(
    deck: list[Card],
    commander: Card,
    partner: Card | None = None,
) -> list[str]:
    """Validate a commander deck. Returns list of errors (empty = valid).

    Rules:
    - Exactly 100 cards including commander(s)
    - All cards within color identity
    - Singleton (no duplicates except basic lands)
    """
    errors = []
    commanders = [commander]
    if partner:
        commanders.append(partner)

    # Check deck size
    total = len(deck) + len(commanders)
    if total != COMMANDER_DECK_SIZE:
        errors.append(
            f"Deck must be exactly {COMMANDER_DECK_SIZE} cards "
            f"(including commander), got {total}"
        )

    # Get combined color identity
    identity = get_color_identity(commander)
    if partner:
        identity |= get_color_identity(partner)

    # Check color identity
    for card in deck:
        if not is_legal_in_deck(card, identity):
            errors.append(
                f"{card.name} has colors outside commander's identity"
            )

    # Check singleton rule
    seen: dict[str, int] = {}
    for card in deck:
        is_basic = (
            SuperType.BASIC in card.supertypes
            and card.card_type == CardType.LAND
        )
        if not is_basic:
            seen[card.name] = seen.get(card.name, 0) + 1
            if seen[card.name] > 1:
                errors.append(f"Duplicate card: {card.name}")

    return errors


def get_commander_tax(state: CommanderState) -> ManaCost:
    """Get the additional cost for casting commander from command zone.

    CR 903.8: Each time a commander is cast from the command zone,
    its cost increases by {2}.
    """
    return ManaCost(generic=2 * state.times_cast)


def can_cast_from_command_zone(
    card: CardInstance,
    commander_state: CommanderState,
) -> bool:
    """Check if a commander can be cast from the command zone."""
    return (
        card.zone == Zone.COMMAND
        and card.instance_id == commander_state.commander_id
    )


def record_commander_cast(state: CommanderState) -> None:
    """Record that a commander was cast (increases tax)."""
    state.times_cast += 1


def record_commander_damage(
    state: CommanderState,
    commander_id: str,
    amount: int,
) -> int:
    """Record combat damage from a specific commander.

    Returns total damage from that commander.
    """
    current = state.commander_damage_taken.get(commander_id, 0)
    new_total = current + amount
    state.commander_damage_taken[commander_id] = new_total
    return new_total


def check_commander_damage_loss(state: CommanderState) -> str | None:
    """Check if any commander has dealt 21+ damage (CR 903.10a).

    Returns the commander_id that killed this player, or None.
    """
    for cmd_id, damage in state.commander_damage_taken.items():
        if damage >= COMMANDER_DAMAGE_THRESHOLD:
            return cmd_id
    return None


def should_go_to_command_zone(
    card: CardInstance,
    commander_state: CommanderState,
    destination: Zone,
) -> bool:
    """Check if a commander should go to command zone instead.

    CR 903.9a: If a commander would be put into exile or
    its owner's graveyard from anywhere, its owner may put
    it into the command zone instead.
    """
    is_commander = card.instance_id == commander_state.commander_id
    if commander_state.partner_id:
        is_commander = is_commander or card.instance_id == commander_state.partner_id
    return is_commander and destination in (Zone.GRAVEYARD, Zone.EXILE)
