"""LLM-based rules text translator using Claude API.

Replaces the regex-based rules_parser.py as the primary translator for
converting MTG natural language rules text into structured effect dicts
that the game engine can execute.

Falls back to the regex parser when:
- No API key is configured
- The API call fails
- The response fails validation
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from mtg_engine.core.keywords import Keyword, KEYWORD_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid engine types — used to validate LLM output
# ---------------------------------------------------------------------------

VALID_EFFECT_TYPES = frozenset({
    "damage", "x_damage", "draw", "gain_life", "lose_life",
    "destroy", "exile", "bounce", "counter", "tap",
    "pump", "add_keyword", "add_mana", "add_counter",
    "mill", "scry", "create_token", "sacrifice",
    "copy_spell", "may", "if_did", "enter_battlefield",
})

VALID_TARGET_KINDS = frozenset({"target", "all", "self", "each_opponent"})

VALID_TARGET_TYPES = frozenset({
    "creature", "player", "any_target", "artifact", "enchantment",
    "permanent", "planeswalker", "spell", "land",
})

VALID_CONTROLLER_QUALIFIERS = frozenset({"you", "opponent"})

VALID_STATE_QUALIFIERS = frozenset({
    "attacking", "blocking", "tapped", "untapped",
})

VALID_TRIGGER_EVENTS = frozenset({
    "enters_battlefield", "leaves_battlefield", "dies",
    "cast", "attacks", "blocks", "deals_combat_damage_to_player",
    "begin_upkeep", "begin_combat", "end_step",
    "gain_life", "lose_life", "draw_card", "damage", "discard",
})

VALID_KEYWORDS = frozenset(k for k in KEYWORD_MAP.keys())

# ---------------------------------------------------------------------------
# System prompt for the LLM
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an MTG rules text translator. You convert Magic: The Gathering card \
rules text into structured JSON effect dictionaries that a game engine can execute.

## Output Format

Return a JSON object with exactly these keys:
{
  "effects": [...],           // List of effect dicts (for instants/sorceries/ETB)
  "keywords": [...],          // List of keyword strings (e.g. ["flying", "first_strike"])
  "triggered_abilities": [...], // List of triggered ability dicts
  "activated_abilities": [...]  // List of activated ability dicts
}

## Effect Dict Schema

Each effect is a dict with "type" and optional fields:

### Effect types and their fields:
- damage: {type, target, amount}
- x_damage: {type, target}  (amount comes from X value at cast time)
- draw: {type, amount}
- gain_life: {type, amount}
- lose_life: {type, target, amount}
- destroy: {type, target}
- exile: {type, target}
- bounce: {type, target}  (return to owner's hand)
- counter: {type, target}  (counter a spell)
- tap: {type, target}
- pump: {type, target, power, toughness}  (e.g. +3/+3 -> power:3, toughness:3)
- add_keyword: {type, target, keyword}
- add_mana: {type, color}  (color is single char: W, U, B, R, G, C)
- add_counter: {type, target, counter_type, amount}
- mill: {type, amount}
- scry: {type, amount}
- create_token: {type, name, power, toughness}  (one dict per token created)
- sacrifice: {type, target}
- copy_spell: {type, copy_target, new_targets}
  - copy_target: "self" or "target_spell"
  - new_targets: true/false
- may: {type, inner_effect}  (wraps an effect the player may choose to do)
- if_did: {type, condition_effect, then_effect}  (then_effect fires only if condition succeeded)

### Target dict schema:
{
  "kind": "target" | "all" | "self" | "each_opponent",
  "target_type": "creature" | "player" | "any_target" | "artifact" | "enchantment" | "permanent" | "planeswalker" | "spell" | "land",
  "controller": "you" | "opponent",   // optional
  "state": "attacking" | "blocking" | "tapped" | "untapped"  // optional
}

- "target" = single targeted thing
- "all" = all permanents of that type (board wipe)
- "self" = the card itself (e.g. "~ gets +1/+1")
- "each_opponent" = each opponent (no target_type needed)

### Triggered ability format:
{
  "trigger": "enters_battlefield" | "dies" | "attacks" | "blocks" | "cast" | "deals_combat_damage_to_player" | "begin_upkeep" | "begin_combat" | "end_step" | "gain_life" | "lose_life" | "draw_card" | "damage" | "discard",
  "source": {"type": "creature"} or {"type": "self"},  // what triggers it
  "effects": [...]  // list of effect dicts
}

- Use "self" for source when the trigger is about this card specifically (~ or "this creature")
- Use a type filter for "whenever a creature..."

### Activated ability format:
{
  "cost": {"tap": true} and/or {"mana": "{2}{R}"} and/or {"sacrifice": "creature"},
  "effects": [...]
}

For loyalty abilities:
{
  "loyalty_cost": N,  // positive for +N, negative for -N, 0 for 0
  "is_loyalty": true,
  "effects": [...]
}

### Keywords:
Use underscore-separated lowercase names: "flying", "first_strike", "double_strike", \
"deathtouch", "trample", "lifelink", "vigilance", "haste", "hexproof", "menace", \
"defender", "flash", "indestructible", "reach", "prowess", "fear", "intimidate", \
"shroud", "shadow", "infect", "wither", "undying", "persist", "flanking", \
"horsemanship", "toxic".

## Rules

1. ~ or CARDNAME refers to the card itself — use target kind "self"
2. "you" = the controller of this card
3. "each opponent" = use target kind "each_opponent"
4. Number words: "a"/"an" = 1, "two" = 2, "three" = 3, etc.
5. "+N: effect" or "−N: effect" at the start = planeswalker loyalty ability
6. "you may X" = wrap X in a may effect
7. "you may X. If you do, Y" = if_did with may condition
8. Compound effects (separated by periods or commas) produce multiple effect dicts
9. For create_token, emit one dict per token (if "create two 1/1 tokens", emit 2 dicts)
10. Return ONLY valid JSON. No explanation, no markdown fences.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_target(target: dict) -> bool:
    """Check that a target dict uses only valid values."""
    kind = target.get("kind")
    if kind not in VALID_TARGET_KINDS:
        return False
    if kind in ("target", "all"):
        if target.get("target_type") not in VALID_TARGET_TYPES:
            return False
    controller = target.get("controller")
    if controller is not None and controller not in VALID_CONTROLLER_QUALIFIERS:
        return False
    state = target.get("state")
    if state is not None and state not in VALID_STATE_QUALIFIERS:
        return False
    return True


def _validate_effect(effect: dict) -> bool:
    """Check that an effect dict uses only valid types and targets."""
    effect_type = effect.get("type")
    if effect_type not in VALID_EFFECT_TYPES:
        logger.warning("LLM produced invalid effect type: %s", effect_type)
        return False
    target = effect.get("target")
    if target is not None and not _validate_target(target):
        logger.warning("LLM produced invalid target: %s", target)
        return False
    # Recursive validation for may/if_did
    if effect_type == "may":
        inner = effect.get("inner_effect")
        if inner and not _validate_effect(inner):
            return False
    if effect_type == "if_did":
        for key in ("condition_effect", "then_effect"):
            sub = effect.get(key)
            if sub and not _validate_effect(sub):
                return False
    return True


def _validate_triggered(ability: dict) -> bool:
    """Validate a triggered ability dict."""
    trigger = ability.get("trigger")
    if trigger not in VALID_TRIGGER_EVENTS:
        logger.warning("LLM produced invalid trigger event: %s", trigger)
        return False
    effects = ability.get("effects", [])
    return all(_validate_effect(e) for e in effects)


def _validate_activated(ability: dict) -> bool:
    """Validate an activated ability dict."""
    effects = ability.get("effects", [])
    return all(_validate_effect(e) for e in effects)


def _validate_result(result: dict) -> bool:
    """Validate the full LLM translation result."""
    for effect in result.get("effects", []):
        if not _validate_effect(effect):
            return False
    for keyword in result.get("keywords", []):
        if keyword not in VALID_KEYWORDS:
            logger.warning("LLM produced invalid keyword: %s", keyword)
            return False
    for triggered in result.get("triggered_abilities", []):
        if not _validate_triggered(triggered):
            return False
    for activated in result.get("activated_abilities", []):
        if not _validate_activated(activated):
            return False
    return True


def _normalize_result(result: dict) -> dict:
    """Convert LLM output into the exact format expected by the engine.

    Mainly converts keyword strings to Keyword enum values.
    """
    keywords = set()
    for kw_name in result.get("keywords", []):
        if kw_name in KEYWORD_MAP:
            keywords.add(KEYWORD_MAP[kw_name])
    result["keywords"] = keywords
    return result


# ---------------------------------------------------------------------------
# LLM API call
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Get Anthropic API key from environment."""
    return os.environ.get("ANTHROPIC_API_KEY")


def _call_llm(rules_text: str, api_key: str | None = None) -> dict | None:
    """Call Claude API to translate rules text, return parsed dict or None on failure."""
    key = api_key or _get_api_key()
    if not key:
        logger.debug("No ANTHROPIC_API_KEY set, skipping LLM parser")
        return None

    if anthropic is None:
        logger.debug("anthropic package not installed, skipping LLM parser")
        return None

    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Translate this MTG rules text:\n\n{rules_text}"}
            ],
        )
        raw_text = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines)

        result = json.loads(raw_text)

        # Ensure expected keys exist
        result.setdefault("effects", [])
        result.setdefault("keywords", [])
        result.setdefault("triggered_abilities", [])
        result.setdefault("activated_abilities", [])

        return result

    except json.JSONDecodeError as e:
        logger.warning("LLM returned invalid JSON: %s", e)
        return None
    except Exception as e:
        logger.warning("LLM API call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public API  (same signature as rules_parser.translate_rules_text)
# ---------------------------------------------------------------------------

def translate_rules_text_llm(
    rules_text: str,
    *,
    api_key: str | None = None,
    fallback: bool = True,
) -> dict:
    """Translate MTG rules text into structured effects using Claude.

    Args:
        rules_text: Natural language MTG rules text.
        api_key: Optional API key override (otherwise uses ANTHROPIC_API_KEY env var).
        fallback: If True (default), fall back to regex parser on failure.

    Returns:
        Dict with keys: effects, keywords, triggered_abilities, activated_abilities.
    """
    result = _call_llm(rules_text, api_key=api_key)

    if result is not None:
        if _validate_result(result):
            logger.debug("LLM translation succeeded for: %s", rules_text[:80])
            return _normalize_result(result)
        else:
            logger.warning(
                "LLM translation failed validation for: %s — falling back",
                rules_text[:80],
            )

    # Fallback to regex parser
    if fallback:
        from mtg_engine.dsl.rules_parser import translate_rules_text
        return translate_rules_text(rules_text)

    # No fallback — return empty
    return {
        "effects": [],
        "keywords": set(),
        "triggered_abilities": [],
        "activated_abilities": [],
    }
