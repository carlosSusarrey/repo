"""Poison counters, infect, and toxic mechanics.

CR 704.5c: A player with 10 or more poison counters loses the game (SBA).
CR 702.91 (Infect): Damage to creatures is dealt as -1/-1 counters;
  damage to players is dealt as poison counters instead of life loss.
CR 702.164 (Toxic N): When this creature deals combat damage to a player,
  that player gets N poison counters (in addition to normal damage).
CR 702.82 (Wither): Damage to creatures is dealt as -1/-1 counters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.keywords import Keyword


POISON_LOSS_THRESHOLD = 10


def get_poison_counters(player: Any) -> int:
    """Get the number of poison counters on a player."""
    return getattr(player, 'poison_counters', 0)


def add_poison_counters(player: Any, count: int) -> int:
    """Add poison counters to a player. Returns new total."""
    current = getattr(player, 'poison_counters', 0)
    new_total = current + count
    player.poison_counters = new_total
    return new_total


def check_poison_loss(player: Any) -> bool:
    """Check if a player has lost due to poison (CR 704.5c).

    Returns True if the player should lose.
    """
    return get_poison_counters(player) >= POISON_LOSS_THRESHOLD


def apply_infect_damage_to_player(
    source: CardInstance,
    player: Any,
    amount: int,
) -> dict[str, Any]:
    """Apply infect damage to a player (poison counters instead of life loss).

    CR 702.91b: Damage dealt to a player by a source with infect
    causes that player to get that many poison counters.
    """
    if amount <= 0:
        return {"poison_added": 0}

    new_total = add_poison_counters(player, amount)
    return {"poison_added": amount, "total_poison": new_total}


def apply_infect_damage_to_creature(
    source: CardInstance,
    target: CardInstance,
    amount: int,
) -> dict[str, Any]:
    """Apply infect damage to a creature (-1/-1 counters instead of damage).

    CR 702.91a: Damage dealt to a creature by a source with infect
    isn't marked on that creature. Instead, it causes that many
    -1/-1 counters to be put on that creature.
    """
    if amount <= 0:
        return {"counters_added": 0}

    current = target.counters.get("-1/-1", 0)
    target.counters["-1/-1"] = current + amount
    return {"counters_added": amount}


def apply_wither_damage_to_creature(
    source: CardInstance,
    target: CardInstance,
    amount: int,
) -> dict[str, Any]:
    """Apply wither damage to a creature (-1/-1 counters instead of damage).

    CR 702.82: Damage dealt to a creature by a source with wither
    isn't marked on that creature. Instead, it causes that many
    -1/-1 counters to be put on that creature.
    """
    # Wither is the same as infect's creature portion
    return apply_infect_damage_to_creature(source, target, amount)


def apply_toxic_damage(
    source: CardInstance,
    player: Any,
    toxic_n: int,
) -> dict[str, Any]:
    """Apply toxic effect after combat damage to a player.

    CR 702.164: Whenever a creature with toxic N deals combat damage
    to a player, that player gets N poison counters.
    Toxic is IN ADDITION to normal damage (unlike infect).
    """
    if toxic_n <= 0:
        return {"poison_added": 0}

    new_total = add_poison_counters(player, toxic_n)
    return {"poison_added": toxic_n, "total_poison": new_total}


def has_infect(card: CardInstance) -> bool:
    """Check if a card has infect."""
    return card.has_keyword(Keyword.INFECT)


def has_wither(card: CardInstance) -> bool:
    """Check if a card has wither (or infect, which includes wither)."""
    return card.has_keyword(Keyword.WITHER) or card.has_keyword(Keyword.INFECT)


def has_toxic(card: CardInstance) -> bool:
    """Check if a card has toxic."""
    return card.has_keyword(Keyword.TOXIC)


def get_toxic_amount(card: CardInstance) -> int:
    """Get the toxic N value for a card.

    Stored in keyword_params as Keyword.TOXIC -> int.
    """
    return card.card.keyword_params.get(Keyword.TOXIC, 0)


def should_deal_poison(source: CardInstance) -> bool:
    """Check if damage from this source should deal poison instead of life loss."""
    return has_infect(source)


def should_deal_minus_counters(source: CardInstance) -> bool:
    """Check if damage from this source deals -1/-1 counters to creatures."""
    return has_infect(source) or has_wither(source)
