"""Equipment and Aura attachment system.

Handles equip costs, attach/detach logic, and enchant targeting.
CR 301.5 (Equipment), CR 303.4 (Auras)
"""

from __future__ import annotations

from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


def can_equip(equipment: CardInstance, target: CardInstance) -> bool:
    """Check if an equipment can be attached to a target creature.

    CR 301.5a: Equipment can only be attached to creatures.
    CR 301.5c: Equipment can't equip itself.
    CR 301.5d: Only on battlefield.
    """
    if equipment.zone != Zone.BATTLEFIELD:
        return False
    if target.zone != Zone.BATTLEFIELD:
        return False
    if not target.card.is_creature:
        return False
    if equipment.instance_id == target.instance_id:
        return False
    if equipment.card.card_type != CardType.ARTIFACT:
        return False
    if "Equipment" not in equipment.card.subtypes:
        return False
    # Must share controller for equip (not for attach via spell)
    if equipment.controller_index != target.controller_index:
        return False
    return True


def can_enchant(aura: CardInstance, target: CardInstance) -> bool:
    """Check if an aura can legally be attached to a target.

    Only checks type-based restrictions (enchant creature, enchant land, etc.).
    Does NOT check hexproof/shroud/ward/protection — those are targeting
    restrictions enforced during casting, not attachment. An aura entering
    the battlefield without being cast (e.g. reanimation) skips targeting
    entirely and just needs a legal object to attach to (CR 303.4f).
    """
    if aura.zone != Zone.BATTLEFIELD and aura.zone != Zone.STACK:
        return False
    if target.zone != Zone.BATTLEFIELD:
        return False
    if aura.instance_id == target.instance_id:
        return False
    if aura.card.card_type != CardType.ENCHANTMENT:
        return False
    if "Aura" not in aura.card.subtypes:
        return False

    # Check enchant restriction from subtypes/rules
    enchant_type = _get_enchant_type(aura)
    if enchant_type == "creature" and not target.card.is_creature:
        return False
    if enchant_type == "artifact" and target.card.card_type != CardType.ARTIFACT:
        return False
    if enchant_type == "land" and not target.card.is_land:
        return False
    if enchant_type == "enchantment" and target.card.card_type != CardType.ENCHANTMENT:
        return False

    return True


def _get_enchant_type(aura: CardInstance) -> str:
    """Determine what an aura can enchant based on its definition."""
    # Check effects for explicit enchant type
    for effect in aura.card.effects:
        if effect.get("type") == "enchant":
            return effect.get("target_type", "permanent")

    # Default: can enchant any permanent
    return "permanent"


def attach(source: CardInstance, target: CardInstance) -> bool:
    """Attach source (equipment/aura) to target.

    Returns True if attachment was successful.
    """
    # Detach from current target if any
    if source.attached_to is not None:
        detach(source, None)

    source.attached_to = target.instance_id
    if source.instance_id not in target.attachments:
        target.attachments.append(source.instance_id)

    return True


def detach(source: CardInstance, old_target: CardInstance | None) -> None:
    """Detach source from its current target."""
    if old_target is not None:
        if source.instance_id in old_target.attachments:
            old_target.attachments.remove(source.instance_id)
    source.attached_to = None


def get_equipment_bonuses(card: CardInstance, all_cards: dict[str, CardInstance]) -> dict[str, Any]:
    """Calculate total bonuses from all equipment attached to a creature.

    Returns dict with power_mod, toughness_mod, and granted_keywords.
    """
    result: dict[str, Any] = {
        "power_mod": 0,
        "toughness_mod": 0,
        "keywords": set(),
    }

    for attachment_id in card.attachments:
        attachment = all_cards.get(attachment_id)
        if attachment is None or attachment.zone != Zone.BATTLEFIELD:
            continue

        is_equipment = (
            attachment.card.card_type == CardType.ARTIFACT
            and "Equipment" in attachment.card.subtypes
        )
        is_aura = (
            attachment.card.card_type == CardType.ENCHANTMENT
            and "Aura" in attachment.card.subtypes
        )

        if not is_equipment and not is_aura:
            continue

        # Apply static effects from the attachment
        for effect in attachment.card.effects:
            if effect.get("type") == "pump":
                result["power_mod"] += effect.get("power", 0)
                result["toughness_mod"] += effect.get("toughness", 0)
            elif effect.get("type") == "add_keyword":
                kw_name = effect.get("keyword", "")
                from mtg_engine.core.keywords import KEYWORD_MAP
                if kw_name in KEYWORD_MAP:
                    result["keywords"].add(KEYWORD_MAP[kw_name])

    return result


def check_equipment_fall_off(
    cards: list[CardInstance],
    find_card: callable,
) -> list[str]:
    """Check for equipment/auras that need to fall off.

    CR 301.5c: If equipped creature leaves battlefield, equipment stays.
    CR 303.4c: If enchanted permanent leaves, aura goes to graveyard.

    Returns descriptions of actions taken.
    """
    actions = []

    for card in cards:
        if card.zone != Zone.BATTLEFIELD:
            continue
        if card.attached_to is None:
            continue

        target = find_card(card.attached_to)

        # Target gone or left battlefield
        if target is None or target.zone != Zone.BATTLEFIELD:
            is_equipment = (
                card.card.card_type == CardType.ARTIFACT
                and "Equipment" in card.card.subtypes
            )

            if is_equipment:
                # Equipment stays on battlefield, just unattached
                card.attached_to = None
                actions.append(f"{card.name} becomes unattached (equipped creature left)")
            else:
                # Auras go to graveyard (handled by SBA in game_state)
                pass

        # Target is no longer a legal object (e.g., stopped being a creature)
        elif card.card.card_type == CardType.ENCHANTMENT and "Aura" in card.card.subtypes:
            enchant_type = _get_enchant_type(card)
            if enchant_type == "creature" and not target.card.is_creature:
                # Will be caught by SBA
                pass

    return actions
