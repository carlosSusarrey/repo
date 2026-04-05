"""Centralized filter vocabulary for targets, triggers, and replacement effects.

Provides shared constants and matching logic used by:
- Trigger source filters (when(event, filter): ...)
- Target qualifiers (target creature you don't control)
- Replacement effect scoping (replace(event, scope): ...)
- Rules text translation (natural language -> effect dicts)
- Unified type matching with include/exclude filters
"""

from __future__ import annotations

from typing import Any

from mtg_engine.core.enums import CardType


# ---------------------------------------------------------------------------
# Filter vocabulary
# ---------------------------------------------------------------------------

# Relation keywords: relationship between a source/target and the controller
RELATION_KEYWORDS = {"self", "another", "any", "you"}

# Card type keywords: filter by permanent/card type
CARD_TYPE_KEYWORDS = {
    "creature", "artifact", "enchantment", "planeswalker",
    "land", "battle", "kindred",
}

# Token status keywords
TOKEN_KEYWORDS = {"token", "nontoken"}

# Controller qualifiers: who controls the target
# Used in target dicts as {"controller": "opponent"} etc.
CONTROLLER_QUALIFIERS = {"you", "opponent"}

# Combat state qualifiers: filter by a permanent's combat/tap status
# Used in target dicts as {"state": "attacking"} etc.
STATE_QUALIFIERS = {
    "attacking", "blocking", "blocked", "unblocked",
    "tapped", "untapped",
}

# All recognized filter keywords
ALL_FILTER_KEYWORDS = RELATION_KEYWORDS | CARD_TYPE_KEYWORDS | TOKEN_KEYWORDS


# ---------------------------------------------------------------------------
# Type hierarchy — used by matches_card_type()
# ---------------------------------------------------------------------------

# String name → CardType enum
CARD_TYPE_MAP = {
    "creature": CardType.CREATURE,
    "artifact": CardType.ARTIFACT,
    "enchantment": CardType.ENCHANTMENT,
    "planeswalker": CardType.PLANESWALKER,
    "land": CardType.LAND,
    "battle": CardType.BATTLE,
    "kindred": CardType.KINDRED,
    "instant": CardType.INSTANT,
    "sorcery": CardType.SORCERY,
}

# Supertypes: "permanent" and "spell" expand to these concrete types
PERMANENT_TYPES = frozenset({
    CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT,
    CardType.PLANESWALKER, CardType.LAND, CardType.BATTLE,
})
SPELL_TYPES = frozenset({
    CardType.INSTANT, CardType.SORCERY, CardType.CREATURE,
    CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER,
})

# Valid type atoms for the DSL (used in grammar and validation)
VALID_TYPE_ATOMS = frozenset({
    "creature", "player", "any_target", "artifact", "enchantment",
    "permanent", "spell", "planeswalker", "land", "battle", "kindred",
    "instant", "sorcery", "token", "nontoken",
})


# ---------------------------------------------------------------------------
# Unified type matching
# ---------------------------------------------------------------------------

def matches_card_type(
    card: Any,
    types: list[str],
    exclude_types: list[str] | None = None,
) -> bool:
    """Check if a card matches a type filter with include/exclude.

    Args:
        card: A Card or CardInstance. Must have card_types (list[CardType])
              and optionally is_token (bool).
        types: List of type names to match (union — card matches if ANY hit).
               Supports: concrete types (creature, artifact, ...), supertypes
               (permanent, spell), and special types (token, nontoken, any_target).
        exclude_types: List of type names to exclude. Card is rejected if it
                       matches ANY exclude type.

    Returns:
        True if the card matches at least one include type and no exclude types.
    """
    # Unwrap CardInstance → Card if needed
    actual_card = card.card if hasattr(card, "card") else card
    card_types = set(actual_card.card_types) if hasattr(actual_card, "card_types") else set()
    is_token = getattr(card, "is_token", False)

    # Check includes — must match at least one
    if not _matches_any_type(card_types, is_token, types):
        return False

    # Check excludes — must match none
    if exclude_types and _matches_any_type(card_types, is_token, exclude_types):
        return False

    return True


def _matches_any_type(
    card_types: set[CardType],
    is_token: bool,
    type_names: list[str],
) -> bool:
    """Check if a card's types match any of the given type names."""
    for name in type_names:
        if name == "any_target":
            return True
        if name == "permanent":
            if card_types & PERMANENT_TYPES:
                return True
        elif name == "spell":
            if card_types & SPELL_TYPES:
                return True
        elif name == "token":
            if is_token:
                return True
        elif name == "nontoken":
            if not is_token:
                return True
        else:
            ct = CARD_TYPE_MAP.get(name)
            if ct is not None and ct in card_types:
                return True
    return False


# ---------------------------------------------------------------------------
# Target normalization — backward compatibility
# ---------------------------------------------------------------------------

def normalize_target(target: dict[str, Any]) -> dict[str, Any]:
    """Normalize a target dict to the types/exclude_types format.

    Converts old-style {"target_type": "creature"} to {"types": ["creature"]}.
    Already-normalized dicts (with "types" key) are returned as-is.
    Non-type-bearing kinds (self, each_opponent) are returned unchanged.
    """
    if not isinstance(target, dict):
        return target

    kind = target.get("kind")

    # self and each_opponent don't have type info
    if kind in ("self", "each_opponent"):
        return target

    # Already normalized
    if "types" in target:
        return target

    # Convert old target_type → types
    result = dict(target)
    old_type = result.pop("target_type", None)
    if old_type is not None:
        result["types"] = [old_type]
    elif kind in ("target", "all"):
        # No type specified — default to any_target for target, permanent for all
        result["types"] = ["any_target"] if kind == "target" else ["permanent"]

    return result


# ---------------------------------------------------------------------------
# Natural language -> state qualifier mapping
# ---------------------------------------------------------------------------

# Patterns in rules text that indicate combat/tap state on targets.
def parse_state_qualifier(text: str) -> str | None:
    """Extract a state qualifier from natural language text.

    Returns "attacking", "blocking", etc., or None if no qualifier found.
    Uses word-boundary matching to avoid "tapped" matching inside "untapped".
    """
    import re
    lower = text.lower()
    # Check longer/prefixed words first to avoid substring matches
    for word in ("untapped", "unblocked", "attacking", "blocking", "blocked", "tapped"):
        if re.search(r"\b" + word + r"\b", lower):
            return word
    return None


# ---------------------------------------------------------------------------
# Natural language -> controller qualifier mapping
# ---------------------------------------------------------------------------

# Patterns in rules text that indicate controller constraints on targets.
# These are checked *after* the base target type is extracted.
CONTROLLER_PHRASES: list[tuple[str, str]] = [
    ("you don't control", "opponent"),
    ("you do not control", "opponent"),
    ("an opponent controls", "opponent"),
    ("your opponent controls", "opponent"),
    ("your opponents control", "opponent"),
    ("you control", "you"),
]


def parse_controller_qualifier(text: str) -> str | None:
    """Extract a controller qualifier from natural language text.

    Returns "you", "opponent", or None if no qualifier found.
    """
    lower = text.lower()
    for phrase, qualifier in CONTROLLER_PHRASES:
        if phrase in lower:
            return qualifier
    return None


# ---------------------------------------------------------------------------
# Source filter parsing (shared by triggers and replacement effects)
# ---------------------------------------------------------------------------

def parse_source_filter(source: str | dict[str, Any]) -> dict[str, Any]:
    """Normalize a source filter to a structured dict.

    Accepts either:
      - A legacy string like "self", "creature", "another"
      - A structured dict with optional keys: relation, card_type, token

    Returns a dict with optional keys:
      - "relation": "self" | "another" | "any" | "you"
      - "card_type": "creature" | "artifact" | ... | "permanent"
      - "token": True (only tokens) | False (only non-tokens)
    """
    if isinstance(source, dict):
        return source

    source = source.strip()
    if source in RELATION_KEYWORDS:
        return {"relation": source}
    if source in CARD_TYPE_KEYWORDS:
        return {"card_type": source}
    if source == "token":
        return {"token": True}
    if source == "nontoken":
        return {"token": False}
    if source == "permanent":
        return {"card_type": "permanent"}
    return {}


def matches_filter(
    source_filter: dict[str, Any],
    card: Any,
    event_data: dict[str, Any],
) -> bool:
    """Check if an event matches a structured source filter.

    Each key in the filter dict is checked independently; all must pass.

    Keys:
      - "relation": relationship between filter owner and event source
          "self"    - event source is this card
          "another" - event source is NOT this card
          "any"     - always matches
          "you"     - event was caused by this card's controller
      - "card_type": event source must be this card type
          "creature", "artifact", "enchantment", "planeswalker",
          "land", "battle", "kindred"
          "permanent" - any permanent type (not instant/sorcery)
      - "token": True means only tokens, False means only non-tokens
    """
    # Check relation
    relation = source_filter.get("relation")
    if relation == "self":
        if event_data.get("card_id") != card.instance_id:
            return False
    elif relation == "another":
        if event_data.get("card_id") == card.instance_id:
            return False
    elif relation == "you":
        if event_data.get("player_index") != card.controller_index:
            return False

    # Check card type — delegate to matches_card_type
    card_type_filter = source_filter.get("card_type")
    if card_type_filter is not None:
        event_card = event_data.get("card")
        if event_card is None:
            return False
        if not matches_card_type(event_card, [card_type_filter]):
            return False

    # Check token status
    token_filter = source_filter.get("token")
    if token_filter is not None:
        event_card = event_data.get("card")
        if event_card is None:
            return False
        is_token = getattr(event_card, "is_token", False)
        if token_filter and not is_token:
            return False
        if not token_filter and is_token:
            return False

    return True


def matches_controller(
    controller_qualifier: str | None,
    target_controller: int,
    caster_controller: int,
) -> bool:
    """Check if a target's controller matches a controller qualifier.

    Args:
        controller_qualifier: "you", "opponent", or None (any controller)
        target_controller: controller_index of the target permanent
        caster_controller: controller_index of the spell/ability's controller
    """
    if controller_qualifier is None:
        return True
    if controller_qualifier == "you":
        return target_controller == caster_controller
    if controller_qualifier == "opponent":
        return target_controller != caster_controller
    return True
