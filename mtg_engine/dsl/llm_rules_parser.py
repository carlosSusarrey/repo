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

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

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
# Effect type documentation — single source of truth for the LLM prompt.
# Keys MUST match VALID_EFFECT_TYPES.  When you add a new effect type to
# the engine, add it to VALID_EFFECT_TYPES *and* EFFECT_TYPE_DOCS so the
# system prompt auto-updates.
# ---------------------------------------------------------------------------

EFFECT_TYPE_DOCS: dict[str, str] = {
    "damage":           "{type, target, amount}",
    "x_damage":         "{type, target}  (amount comes from X value at cast time)",
    "draw":             "{type, amount}",
    "gain_life":        "{type, amount}",
    "lose_life":        "{type, target, amount}",
    "destroy":          "{type, target}",
    "exile":            "{type, target}",
    "bounce":           "{type, target}  (return to owner's hand)",
    "counter":          "{type, target}  (counter a spell)",
    "tap":              "{type, target}",
    "pump":             "{type, target, power, toughness}  (e.g. +3/+3 -> power:3, toughness:3)",
    "add_keyword":      "{type, target, keyword}",
    "add_mana":         "{type, color}  (color is single char: W, U, B, R, G, C)",
    "add_counter":      "{type, target, counter_type, amount}",
    "mill":             "{type, amount}",
    "scry":             "{type, amount}",
    "create_token":     "{type, name, power, toughness}  (one dict per token created)",
    "sacrifice":        "{type, target}",
    "copy_spell":       '{type, copy_target, new_targets}\n  - copy_target: "self" or "target_spell"\n  - new_targets: true/false',
    "may":              "{type, inner_effect}  (wraps an effect the player may choose to do)",
    "if_did":           "{type, condition_effect, then_effect}  (then_effect fires only if condition succeeded)",
    "enter_battlefield": "{type, target}  (move to battlefield)",
}


def _build_system_prompt() -> str:
    """Build the system prompt dynamically from VALID_* sets and EFFECT_TYPE_DOCS.

    This ensures the prompt always reflects the current engine capabilities.
    If a type exists in VALID_EFFECT_TYPES but not EFFECT_TYPE_DOCS, a warning
    is logged and a generic entry is generated.
    """
    # --- Effect types section (auto-generated) ---
    effect_lines = []
    for etype in sorted(VALID_EFFECT_TYPES):
        doc = EFFECT_TYPE_DOCS.get(etype)
        if doc is None:
            logger.warning(
                "Effect type %r in VALID_EFFECT_TYPES but missing from "
                "EFFECT_TYPE_DOCS — LLM prompt will have a generic entry", etype,
            )
            doc = "{type, ...}"
        effect_lines.append(f"- {etype}: {doc}")
    effect_types_block = "\n".join(effect_lines)

    # --- Target schema (auto-generated from sets) ---
    kinds_str = " | ".join(f'"{k}"' for k in sorted(VALID_TARGET_KINDS))
    types_str = " | ".join(f'"{t}"' for t in sorted(VALID_TARGET_TYPES))
    ctrl_str = " | ".join(f'"{c}"' for c in sorted(VALID_CONTROLLER_QUALIFIERS))
    state_str = " | ".join(f'"{s}"' for s in sorted(VALID_STATE_QUALIFIERS))

    # --- Trigger events (auto-generated) ---
    triggers_str = " | ".join(f'"{t}"' for t in sorted(VALID_TRIGGER_EVENTS))

    # --- Keywords (auto-generated) ---
    keywords_str = ", ".join(f'"{k}"' for k in sorted(VALID_KEYWORDS))

    return f"""\
You are an MTG rules text translator. You convert Magic: The Gathering card \
rules text into structured JSON effect dictionaries that a game engine can execute.

## Output Format

Return a JSON object with exactly these keys:
{{
  "effects": [...],           // List of effect dicts (for instants/sorceries/ETB)
  "keywords": [...],          // List of keyword strings (e.g. ["flying", "first_strike"])
  "triggered_abilities": [...], // List of triggered ability dicts
  "activated_abilities": [...]  // List of activated ability dicts
}}

## Effect Dict Schema

Each effect is a dict with "type" and optional fields:

### Effect types and their fields:
{effect_types_block}

### Target dict schema:
{{
  "kind": {kinds_str},
  "target_type": {types_str},
  "controller": {ctrl_str},   // optional
  "state": {state_str}  // optional
}}

- "target" = single targeted thing
- "all" = all permanents of that type (board wipe)
- "self" = the card itself (e.g. "~ gets +1/+1")
- "each_opponent" = each opponent (no target_type needed)

### Triggered ability format:
{{
  "trigger": {triggers_str},
  "source": {{"type": "creature"}} or {{"type": "self"}},  // what triggers it
  "effects": [...]  // list of effect dicts
}}

- Use "self" for source when the trigger is about this card specifically (~ or "this creature")
- Use a type filter for "whenever a creature..."

### Activated ability format:
{{
  "cost": {{"tap": true}} and/or {{"mana": "{{2}}{{R}}"}} and/or {{"sacrifice": "creature"}},
  "effects": [...]
}}

For loyalty abilities:
{{
  "loyalty_cost": N,  // positive for +N, negative for -N, 0 for 0
  "is_loyalty": true,
  "effects": [...]
}}

### Keywords:
Use underscore-separated lowercase names: {keywords_str}.

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
11. "you don't control" or "an opponent controls" → controller: "opponent"
12. "you control" → controller: "you"
13. "attacking", "blocking", "tapped", "untapped" before a type → state qualifier
14. Controller and state qualifiers are OPTIONAL — omit keys entirely when not specified in the rules text.

## Examples

Input: "Flying, first strike, lifelink"
Output: {{"effects": [], "keywords": ["flying", "first_strike", "lifelink"], "triggered_abilities": [], "activated_abilities": []}}

Input: "Deal 3 damage to any target."
Output: {{"effects": [{{"type": "damage", "target": {{"kind": "target", "target_type": "any_target"}}, "amount": 3}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Deal X damage to any target."
Output: {{"effects": [{{"type": "x_damage", "target": {{"kind": "target", "target_type": "any_target"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Draw a card."
Output: {{"effects": [{{"type": "draw", "amount": 1}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Gain 3 life."
Output: {{"effects": [{{"type": "gain_life", "amount": 3}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Each opponent loses 2 life."
Output: {{"effects": [{{"type": "lose_life", "target": {{"kind": "each_opponent"}}, "amount": 2}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Destroy target creature."
Output: {{"effects": [{{"type": "destroy", "target": {{"kind": "target", "target_type": "creature"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Exile target creature an opponent controls."
Output: {{"effects": [{{"type": "exile", "target": {{"kind": "target", "target_type": "creature", "controller": "opponent"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Return target creature to its owner's hand."
Output: {{"effects": [{{"type": "bounce", "target": {{"kind": "target", "target_type": "creature"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Counter target spell."
Output: {{"effects": [{{"type": "counter", "target": {{"kind": "target", "target_type": "spell"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Target creature gets +3/+3 until end of turn."
Output: {{"effects": [{{"type": "pump", "target": {{"kind": "target", "target_type": "creature"}}, "power": 3, "toughness": 3}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "~ gets +2/+2 until end of turn."
Output: {{"effects": [{{"type": "pump", "target": {{"kind": "self"}}, "power": 2, "toughness": 2}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Scry 2."
Output: {{"effects": [{{"type": "scry", "amount": 2}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Mill 3."
Output: {{"effects": [{{"type": "mill", "amount": 3}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Tap target creature."
Output: {{"effects": [{{"type": "tap", "target": {{"kind": "target", "target_type": "creature"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Create a 1/1 Soldier creature token."
Output: {{"effects": [{{"type": "create_token", "name": "Soldier", "power": 1, "toughness": 1}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Create two 1/1 white Soldier creature tokens."
Output: {{"effects": [{{"type": "create_token", "name": "white Soldier", "power": 1, "toughness": 1}}, {{"type": "create_token", "name": "white Soldier", "power": 1, "toughness": 1}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Destroy target attacking creature you don't control."
Output: {{"effects": [{{"type": "destroy", "target": {{"kind": "target", "target_type": "creature", "state": "attacking", "controller": "opponent"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Deal 4 damage to target tapped creature you don't control."
Output: {{"effects": [{{"type": "damage", "target": {{"kind": "target", "target_type": "creature", "state": "tapped", "controller": "opponent"}}, "amount": 4}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Destroy all creatures."
Output: {{"effects": [{{"type": "destroy", "target": {{"kind": "all", "target_type": "creature"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Exile all attacking creatures."
Output: {{"effects": [{{"type": "exile", "target": {{"kind": "all", "target_type": "creature", "state": "attacking"}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "All creatures get +1/+1 until end of turn."
Output: {{"effects": [{{"type": "pump", "target": {{"kind": "all", "target_type": "creature"}}, "power": 1, "toughness": 1}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "When ~ enters the battlefield, draw a card."
Output: {{"effects": [], "keywords": [], "triggered_abilities": [{{"trigger": "enters_battlefield", "source": {{"type": "self"}}, "effects": [{{"type": "draw", "amount": 1}}]}}], "activated_abilities": []}}

Input: "When ~ dies, each opponent loses 2 life."
Output: {{"effects": [], "keywords": [], "triggered_abilities": [{{"trigger": "dies", "source": {{"type": "self"}}, "effects": [{{"type": "lose_life", "target": {{"kind": "each_opponent"}}, "amount": 2}}]}}], "activated_abilities": []}}

Input: "Whenever ~ attacks, deal 1 damage to each opponent."
Output: {{"effects": [], "keywords": [], "triggered_abilities": [{{"trigger": "attacks", "source": {{"type": "self"}}, "effects": [{{"type": "damage", "target": {{"kind": "each_opponent"}}, "amount": 1}}]}}], "activated_abilities": []}}

Input: "At the beginning of your upkeep, draw a card."
Output: {{"effects": [], "keywords": [], "triggered_abilities": [{{"trigger": "begin_upkeep", "source": {{"type": "self"}}, "effects": [{{"type": "draw", "amount": 1}}]}}], "activated_abilities": []}}

Input: "{{T}}: Add {{G}}."
Output: {{"effects": [], "keywords": [], "triggered_abilities": [], "activated_abilities": [{{"cost": {{"tap": true}}, "effects": [{{"type": "add_mana", "color": "G"}}]}}]}}

Input: "{{2}}{{R}}: Deal 2 damage to any target."
Output: {{"effects": [], "keywords": [], "triggered_abilities": [], "activated_abilities": [{{"cost": {{"mana": "{{2}}{{R}}"}}, "effects": [{{"type": "damage", "target": {{"kind": "target", "target_type": "any_target"}}, "amount": 2}}]}}]}}

Input: "Sacrifice a creature: draw a card"
Output: {{"effects": [], "keywords": [], "triggered_abilities": [], "activated_abilities": [{{"cost": {{"sacrifice": "creature"}}, "effects": [{{"type": "draw", "amount": 1}}]}}]}}

Input: "{{T}}, Sacrifice a creature: draw a card"
Output: {{"effects": [], "keywords": [], "triggered_abilities": [], "activated_abilities": [{{"cost": {{"tap": true, "sacrifice": "creature"}}, "effects": [{{"type": "draw", "amount": 1}}]}}]}}

Input: "{{2}}, Sacrifice a creature: draw two cards"
Output: {{"effects": [], "keywords": [], "triggered_abilities": [], "activated_abilities": [{{"cost": {{"mana": "{{2}}", "sacrifice": "creature"}}, "effects": [{{"type": "draw", "amount": 2}}]}}]}}

Input: "+1: Draw a card"
Output: {{"effects": [], "keywords": [], "triggered_abilities": [], "activated_abilities": [{{"loyalty_cost": 1, "is_loyalty": true, "effects": [{{"type": "draw", "amount": 1}}]}}]}}

Input: "\u22123: Destroy target creature"
Output: {{"effects": [], "keywords": [], "triggered_abilities": [], "activated_abilities": [{{"loyalty_cost": -3, "is_loyalty": true, "effects": [{{"type": "destroy", "target": {{"kind": "target", "target_type": "creature"}}}}]}}]}}

Input: "You may draw a card"
Output: {{"effects": [{{"type": "may", "inner_effect": {{"type": "draw", "amount": 1}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "When this creature enters the battlefield, you may draw a card"
Output: {{"effects": [], "keywords": [], "triggered_abilities": [{{"trigger": "enters_battlefield", "source": {{"type": "self"}}, "effects": [{{"type": "may", "inner_effect": {{"type": "draw", "amount": 1}}}}]}}], "activated_abilities": []}}

Input: "You may sacrifice a creature. If you do, draw two cards"
Output: {{"effects": [{{"type": "if_did", "condition_effect": {{"type": "may", "inner_effect": {{"type": "sacrifice", "target": {{"kind": "target", "target_type": "creature"}}}}}}, "then_effect": {{"type": "draw", "amount": 2}}}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Copy this spell"
Output: {{"effects": [{{"type": "copy_spell", "copy_target": "self", "new_targets": false}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Copy this spell and choose new targets"
Output: {{"effects": [{{"type": "copy_spell", "copy_target": "self", "new_targets": true}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Copy target instant or sorcery spell"
Output: {{"effects": [{{"type": "copy_spell", "copy_target": "target_spell", "new_targets": false}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "~ gains flying until end of turn."
Output: {{"effects": [{{"type": "add_keyword", "target": {{"kind": "self"}}, "keyword": "flying"}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Put a +1/+1 counter on ~."
Output: {{"effects": [{{"type": "add_counter", "target": {{"kind": "self"}}, "counter_type": "+1/+1", "amount": 1}}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}}

Input: "Defender. When ~ enters the battlefield, draw a card."
Output: {{"effects": [], "keywords": ["defender"], "triggered_abilities": [{{"trigger": "enters_battlefield", "source": {{"type": "self"}}, "effects": [{{"type": "draw", "amount": 1}}]}}], "activated_abilities": []}}

Input: "Flying. Deal 3 damage to any target."
Output: {{"effects": [{{"type": "damage", "target": {{"kind": "target", "target_type": "any_target"}}, "amount": 3}}], "keywords": ["flying"], "triggered_abilities": [], "activated_abilities": []}}
"""


# Build the prompt once at import time
SYSTEM_PROMPT = _build_system_prompt()


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
# LLM provider configuration
# ---------------------------------------------------------------------------
#
# Provider is selected via the LLM_PROVIDER env var (default: "anthropic").
#
# Anthropic (default):
#   LLM_PROVIDER=anthropic  (or unset)
#   ANTHROPIC_API_KEY=sk-ant-...
#   LLM_MODEL=claude-sonnet-4-20250514  (optional override)
#
# OpenAI-compatible (Ollama, vLLM, llama.cpp, LM Studio, LocalAI, OpenAI, etc.):
#   LLM_PROVIDER=openai
#   LLM_BASE_URL=http://localhost:11434/v1   (your local server)
#   LLM_API_KEY=not-needed                   (some servers ignore this, but the field is required)
#   LLM_MODEL=llama3                         (model name your server knows)
#
# ---------------------------------------------------------------------------

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENAI_MODEL = "gpt-4o"


def _get_llm_config() -> dict[str, str | None]:
    """Read LLM provider configuration from environment variables."""
    return {
        "provider": os.environ.get("LLM_PROVIDER", "anthropic").lower(),
        "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"),
        "base_url": os.environ.get("LLM_BASE_URL"),
        "model": os.environ.get("LLM_MODEL"),
    }


# ---------------------------------------------------------------------------
# LLM API call — multi-provider
# ---------------------------------------------------------------------------

def _call_anthropic(rules_text: str, api_key: str, model: str | None) -> str:
    """Call Anthropic API, return raw response text."""
    if anthropic is None:
        raise RuntimeError("anthropic package not installed — pip install anthropic")
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model or DEFAULT_ANTHROPIC_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Translate this MTG rules text:\n\n{rules_text}"}
        ],
    )
    return response.content[0].text.strip()


def _call_openai_compatible(
    rules_text: str, api_key: str, model: str | None, base_url: str | None
) -> str:
    """Call an OpenAI-compatible API (local or remote), return raw response text."""
    if openai is None:
        raise RuntimeError("openai package not installed — pip install openai")
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model or DEFAULT_OPENAI_MODEL,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Translate this MTG rules text:\n\n{rules_text}"},
        ],
    )
    return response.choices[0].message.content.strip()


def _parse_llm_response(raw_text: str) -> dict | None:
    """Parse raw LLM response text into a result dict."""
    # Strip markdown fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        raw_text = "\n".join(lines)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.warning("LLM returned invalid JSON: %s", e)
        return None

    # Ensure expected keys exist
    result.setdefault("effects", [])
    result.setdefault("keywords", [])
    result.setdefault("triggered_abilities", [])
    result.setdefault("activated_abilities", [])
    return result


def _call_llm(rules_text: str, api_key: str | None = None) -> dict | None:
    """Call configured LLM provider to translate rules text.

    Returns parsed dict or None on failure.
    """
    config = _get_llm_config()
    provider = config["provider"]
    key = api_key or config["api_key"]

    if not key:
        logger.debug("No API key configured, skipping LLM parser")
        return None

    try:
        if provider == "openai":
            raw = _call_openai_compatible(
                rules_text, key, config["model"], config["base_url"],
            )
        else:
            # Default: anthropic
            raw = _call_anthropic(rules_text, key, config["model"])

        return _parse_llm_response(raw)

    except Exception as e:
        logger.warning("LLM API call failed (%s): %s", provider, e)
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
    """Translate MTG rules text into structured effects using an LLM.

    The LLM provider is configured via environment variables:
      LLM_PROVIDER  — "anthropic" (default) or "openai" (for any OpenAI-compatible server)
      LLM_BASE_URL  — base URL for OpenAI-compatible servers (e.g. http://localhost:11434/v1)
      LLM_API_KEY   — API key (falls back to ANTHROPIC_API_KEY)
      LLM_MODEL     — model name override

    Args:
        rules_text: Natural language MTG rules text.
        api_key: Optional API key override (otherwise uses env vars).
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
