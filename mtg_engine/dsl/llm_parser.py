"""LLM-powered translation of MTG rules text into structured effect dicts.

Uses Ollama to parse natural language card text into the same format as
rules_parser.translate_rules_text(), enabling AI-powered card parsing that
handles novel and complex card text beyond the regex parser's coverage.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from mtg_engine.core.keywords import Keyword, KEYWORD_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known vocabulary — used for validation
# ---------------------------------------------------------------------------

_VALID_EFFECT_TYPES = frozenset({
    "damage", "x_damage", "draw", "gain_life", "lose_life",
    "destroy", "exile", "bounce", "counter", "tap",
    "pump", "add_keyword", "add_mana", "add_counter",
    "mill", "scry", "create_token", "sacrifice",
    "may", "if_did", "copy_spell",
})

_VALID_TARGET_KINDS = frozenset({"target", "all", "self", "each_opponent"})

_VALID_TARGET_TYPES = frozenset({
    "creature", "player", "any_target", "artifact", "enchantment",
    "permanent", "spell", "planeswalker", "land", "battle", "kindred",
    "instant", "sorcery", "token", "nontoken",
})

_VALID_TRIGGER_EVENTS = frozenset({
    "enters_battlefield", "leaves_battlefield", "dies",
    "attacks", "blocks", "cast",
    "begin_upkeep", "end_step",
    "deals_combat_damage_to_player",
    "draw_card", "gain_life", "lose_life", "discard",
    "damage", "enters_graveyard", "is_exiled", "enters_hand",
    "zone_change", "counter_placed", "land_enters",
    "transforms", "level_up", "put_on_top", "put_on_bottom",
})

_VALID_KEYWORDS = frozenset(KEYWORD_MAP.keys())

# ---------------------------------------------------------------------------
# Shared DSL specification — single source of truth for both prompts
# ---------------------------------------------------------------------------

_DSL_SPEC = """\
# MTG Rules Engine — DSL Specification

This is a CLOSED vocabulary. You may ONLY use the exact function names, keywords, \
event names, and target types listed below. Do NOT invent new ones. Do NOT use \
synonyms. If an MTG concept is not listed here, skip it or approximate with the \
closest available function.

## EFFECT FUNCTIONS — Complete List

Each effect is a function call with a FIXED number of arguments. Do NOT add extra arguments.

### Effects that take a TARGET only (exactly 1 argument):
    destroy(TARGET)          — destroy a permanent
    exile(TARGET)            — exile a permanent
    bounce(TARGET)           — return to owner's hand ("bounce" is the ONLY name — NOT "return")
    counter(TARGET)          — counter a spell on the stack
    tap(TARGET)              — tap a permanent
    sacrifice(TARGET)        — sacrifice a permanent

### Effects that take a TARGET and a NUMBER (exactly 2 arguments):
    damage(TARGET, NUMBER)   — deal damage
    lose_life(TARGET, NUMBER) — target loses life
    pump(TARGET, +P/+T)      — temporary P/T boost until end of turn, e.g. pump(self, +3/+3)
    add_keyword(TARGET, KEYWORD) — grant a keyword until end of turn

### Effects that take a NUMBER only (exactly 1 argument):
    draw(NUMBER)             — draw cards
    gain_life(NUMBER)        — you gain life
    mill(NUMBER)             — mill cards from library
    scry(NUMBER)             — scry (look at top N)

### Effects with special signatures:
    x_damage(TARGET)         — deal X damage (for X spells)
    add_mana(COLOR)          — add one mana; COLOR is one of: W U B R G C
    add_counter(TARGET, "COUNTER_TYPE", NUMBER) — e.g. add_counter(self, "+1/+1", 2)
    create_token("NAME", POWER/TOUGHNESS) — e.g. create_token("Soldier", 1/1)
    may(EFFECT)              — optional effect the controller may choose
    if_did(EFFECT, EFFECT)   — conditional: if first effect succeeds, do second
    copy_spell(self)         — copy this spell
    copy_spell(target_spell) — copy target spell

### Chaining multiple effects:
    Use semicolons: damage(target(any_target), 3); draw(1)

## TARGET SYNTAX — Complete List

Targets support type unions (|) and negation (!) for compound targeting.

    target(TYPE_EXPR)                       — single target
    target(TYPE_EXPR, CONTROLLER)           — with controller qualifier
    target(TYPE_EXPR, STATE)                — with state qualifier
    target(TYPE_EXPR, CONTROLLER, STATE)    — with both qualifiers
    all(TYPE_EXPR)                          — all matching permanents
    all(TYPE_EXPR, CONTROLLER)              — all matching with controller
    all(TYPE_EXPR, STATE)                   — all matching with state
    all(TYPE_EXPR, CONTROLLER, STATE)       — all matching with both
    self                                    — this card itself (no parentheses)
    each_opponent                           — each opponent (no parentheses)

### TYPE_EXPR syntax:
    TYPE_EXPR is one or more type atoms separated by |
    Prefix a type with ! to exclude it.

    Examples:
        creature                    — just creatures
        permanent | !land           — nonland permanents
        creature | planeswalker     — creatures or planeswalkers
        spell | !creature           — noncreature spells
        creature | !token           — nontoken creatures
        artifact | enchantment      — artifacts or enchantments

### Valid type atoms (and ONLY these):
    creature  player  any_target  artifact  enchantment  permanent  spell
    planeswalker  land  battle  kindred  instant  sorcery  token  nontoken

### Valid CONTROLLERs (and ONLY these):
    you  opponent

### Valid STATEs (and ONLY these):
    attacking  blocking  blocked  unblocked  tapped  untapped

## KEYWORDS — Complete List

    flying, reach, first_strike, double_strike, deathtouch, trample, lifelink,
    vigilance, haste, hexproof, menace, defender, flash, indestructible, ward,
    protection, prowess, cycling, kicker, flashback, equip, fear, intimidate,
    shroud, shadow, horsemanship, landwalk, flanking, morph, disguise, transform,
    toxic, wither, infect, undying, persist

## TRIGGER EVENTS — Complete List

    enters_battlefield  leaves_battlefield  dies  attacks  blocks  cast
    begin_upkeep  end_step  deals_combat_damage_to_player
    draw_card  gain_life  lose_life  discard  damage
    enters_graveyard  is_exiled  enters_hand  zone_change
    counter_placed  land_enters  transforms  level_up  put_on_top  put_on_bottom

## SOURCE FILTERS (for triggered abilities)

    self  you  any  another
    creature  artifact  enchantment  planeswalker  land  battle  kindred
    token  nontoken  permanent

## CARD TYPES
    Creature  Instant  Sorcery  Enchantment  Artifact  Planeswalker  Land  Battle  Kindred

## SUPERTYPES
    Legendary  Basic  Snow

## MANA SYMBOLS
    {W} {U} {B} {R} {G} {C} {X} {0} {1} {2} ... {20}
    Hybrid: {W/U} {U/B} {B/R} {R/G} {G/W} {W/B} {U/R} {B/G} {R/W} {G/U}
    Phyrexian: {W/P} {U/P} {B/P} {R/P} {G/P}

## MANA COLORS (for add_mana)
    W  U  B  R  G  C

## REPLACEMENT EFFECTS
    replace(EVENT): enter_tapped
    replace(EVENT): add_counters("TYPE", NUMBER)
    replace(EVENT): prevent
    replace(EVENT): prevent_damage(NUMBER)
    replace(EVENT): prevent_damage
    replace(EVENT): double_life
    Optional scope: replace(EVENT, self): ... or replace(EVENT, any): ...

## COMMON MISTAKES TO AVOID
- "return" is NOT a function. Use bounce() for returning to hand.
- "deal_damage" is NOT a function. Use damage().
- "create" is NOT a function. Use create_token().
- "discard" is NOT an effect function. Use sacrifice() for permanents.
- Do NOT add extra arguments: bounce(target(creature)) is correct, bounce(target(creature), owner) is WRONG.
- Do NOT invent functions like heal(), burn(), summon(), draw_cards(), etc.
- Do NOT use markdown, comments, or explanations in the output.
- gain_life takes ONLY a number: gain_life(3). It does NOT take a target.
- lose_life REQUIRES a target: lose_life(each_opponent, 2).
- pump requires signed P/T: pump(target(creature), +3/+3), NOT pump(target(creature), 3, 3).
- Do NOT combine types into one word: "nonland_permanent" is WRONG. Use permanent | !land.
- Do NOT invent new type atoms: "nonland" alone is not a type. Use permanent | !land.
- "noncreature spell" → spell | !creature, NOT "noncreature_spell" or "noncreature".
"""

# ---------------------------------------------------------------------------
# System prompt for rules text → JSON parsing
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an MTG rules text parser. Convert Magic: The Gathering card rules text \
into structured JSON. Output ONLY valid JSON with no explanation or markdown.

""" + _DSL_SPEC + """

## YOUR TASK: JSON Output

Return a JSON object with exactly these four keys:
{
  "effects": [],
  "keywords": [],
  "triggered_abilities": [],
  "activated_abilities": []
}

### Effect JSON format:
Each effect is {"type": "<effect_name>", ...} with fields matching the DSL function signature:
- damage: {"type":"damage", "target":{...}, "amount":N}
- draw: {"type":"draw", "amount":N}
- gain_life: {"type":"gain_life", "amount":N}
- lose_life: {"type":"lose_life", "target":{...}, "amount":N}
- destroy/exile/bounce/counter/tap/sacrifice: {"type":"<name>", "target":{...}}
- pump: {"type":"pump", "target":{...}, "power":N, "toughness":N}
- add_keyword: {"type":"add_keyword", "target":{...}, "keyword":"<name>"}
- add_mana: {"type":"add_mana", "color":"<W|U|B|R|G|C>"}
- add_counter: {"type":"add_counter", "target":{...}, "counter_type":"<type>", "amount":N}
- mill: {"type":"mill", "amount":N}
- scry: {"type":"scry", "amount":N}
- create_token: {"type":"create_token", "name":"<name>", "power":N, "toughness":N}
- may: {"type":"may", "inner_effect":{...}}
- if_did: {"type":"if_did", "condition_effect":{...}, "then_effect":{...}}
- copy_spell: {"type":"copy_spell", "copy_target":"self"}
- x_damage: {"type":"x_damage", "target":{...}}

### Target JSON format:
{"kind":"target|all|self|each_opponent", "types":["<type>", ...], "exclude_types":["<type>", ...], "controller":"you|opponent", "state":"<state>"}
- "kind" is always required
- "types" is required for "target" and "all" kinds — an array of type atoms (union: match any)
- "exclude_types" is optional — an array of type atoms to exclude (reject if any match)
- "controller" and "state" are optional
- Use "types":["permanent"],"exclude_types":["land"] for "nonland permanent"
- Use "types":["creature","planeswalker"] for "creature or planeswalker"

### Triggered ability JSON format:
{"trigger":"<event>", "source":{"relation":"self|any|another|you", "card_type":"<type>"}, "effects":[...]}

### Activated ability JSON format:
{"cost":{"mana":"<cost>", "tap":true/false, "sacrifice":"<type>"}, "effects":[...]}
For loyalty abilities: {"cost":{"loyalty_cost":N, "is_loyalty":true}, "effects":[...]}

## Examples

Input: "Deal 3 damage to any target."
Output: {"effects":[{"type":"damage","target":{"kind":"target","types":["any_target"]},"amount":3}],"keywords":[],"triggered_abilities":[],"activated_abilities":[]}

Input: "When this creature enters the battlefield, draw a card."
Output: {"effects":[],"keywords":[],"triggered_abilities":[{"trigger":"enters_battlefield","source":{"relation":"self"},"effects":[{"type":"draw","amount":1}]}],"activated_abilities":[]}

Input: "{T}: Add {G}."
Output: {"effects":[],"keywords":[],"triggered_abilities":[],"activated_abilities":[{"cost":{"tap":true},"effects":[{"type":"add_mana","color":"G"}]}]}

Input: "Flying, lifelink. When this creature dies, each opponent loses 2 life."
Output: {"effects":[],"keywords":["flying","lifelink"],"triggered_abilities":[{"trigger":"dies","source":{"relation":"self"},"effects":[{"type":"lose_life","target":{"kind":"each_opponent"},"amount":2}]}],"activated_abilities":[]}

Input: "Return target nonland permanent to its owner's hand."
Output: {"effects":[{"type":"bounce","target":{"kind":"target","types":["permanent"],"exclude_types":["land"]}}],"keywords":[],"triggered_abilities":[],"activated_abilities":[]}

Input: "+1: Draw a card. -3: Destroy target creature."
Output: {"effects":[],"keywords":[],"triggered_abilities":[],"activated_abilities":[{"cost":{"loyalty_cost":1,"is_loyalty":true},"effects":[{"type":"draw","amount":1}]},{"cost":{"loyalty_cost":-3,"is_loyalty":true},"effects":[{"type":"destroy","target":{"kind":"target","types":["creature"]}}]}]}

Input: "Destroy all creatures. Each player loses 3 life."
Output: {"effects":[{"type":"destroy","target":{"kind":"all","types":["creature"]}},{"type":"lose_life","target":{"kind":"each_opponent"},"amount":3}],"keywords":[],"triggered_abilities":[],"activated_abilities":[]}

Input: "Sacrifice a creature: Draw a card."
Output: {"effects":[],"keywords":[],"triggered_abilities":[],"activated_abilities":[{"cost":{"sacrifice":{"types":["creature"]}},"effects":[{"type":"draw","amount":1}]}]}

Input: "Destroy target creature or planeswalker."
Output: {"effects":[{"type":"destroy","target":{"kind":"target","types":["creature","planeswalker"]}}],"keywords":[],"triggered_abilities":[],"activated_abilities":[]}
"""


# ---------------------------------------------------------------------------
# Ollama API call
# ---------------------------------------------------------------------------

def _call_ollama(
    rules_text: str,
    model: str,
    base_url: str,
    timeout: float,
) -> str:
    """Call Ollama chat API and return the raw response content string."""
    resp = requests.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Parse this MTG rules text:\n\n{rules_text}"},
            ],
            "stream": False,
            "format": "json",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ---------------------------------------------------------------------------
# Validation & normalization
# ---------------------------------------------------------------------------

def _validate_target(target: Any) -> dict | None:
    """Validate and normalize a target dict. Returns None if invalid.

    Accepts both old format (target_type string) and new format (types/exclude_types lists).
    Always normalizes to the new types/exclude_types format.
    """
    if not isinstance(target, dict):
        return None
    kind = target.get("kind")
    if kind not in _VALID_TARGET_KINDS:
        return None
    result = {"kind": kind}
    if kind in ("target", "all"):
        # Handle both old target_type and new types/exclude_types
        types = target.get("types")
        if types is None:
            # Convert old format
            tt = target.get("target_type")
            if tt in _VALID_TARGET_TYPES:
                types = [tt]
            else:
                return None
        # Validate all type atoms
        if not isinstance(types, list) or not types:
            return None
        valid_types = [t for t in types if t in _VALID_TARGET_TYPES]
        if not valid_types:
            return None
        result["types"] = valid_types

        exclude_types = target.get("exclude_types")
        if exclude_types:
            if isinstance(exclude_types, list):
                valid_excludes = [t for t in exclude_types if t in _VALID_TARGET_TYPES]
                if valid_excludes:
                    result["exclude_types"] = valid_excludes
    ctrl = target.get("controller")
    if ctrl in ("you", "opponent"):
        result["controller"] = ctrl
    state = target.get("state")
    if state in ("attacking", "blocking", "blocked", "unblocked", "tapped", "untapped"):
        result["state"] = state
    return result


def _validate_effect(effect: Any) -> dict | None:
    """Validate and normalize a single effect dict. Returns None if invalid."""
    if not isinstance(effect, dict):
        return None
    etype = effect.get("type")
    if etype not in _VALID_EFFECT_TYPES:
        return None

    result: dict[str, Any] = {"type": etype}

    # Target-bearing effects
    if "target" in effect:
        t = _validate_target(effect["target"])
        if t:
            result["target"] = t

    # Numeric fields
    for field in ("amount", "power", "toughness"):
        if field in effect and isinstance(effect[field], (int, float)):
            result[field] = int(effect[field])

    # String fields
    for field in ("keyword", "color", "counter_type", "name", "copy_target"):
        if field in effect and isinstance(effect[field], str):
            result[field] = effect[field]

    # Nested effects (may, if_did)
    if etype == "may" and "inner_effect" in effect:
        inner = _validate_effect(effect["inner_effect"])
        if inner:
            result["inner_effect"] = inner
    if etype == "if_did":
        for key in ("condition_effect", "then_effect"):
            if key in effect:
                nested = _validate_effect(effect[key])
                if nested:
                    result[key] = nested

    return result


def _validate_and_normalize(raw: str) -> dict:
    """Parse JSON response and normalize to the expected output format.

    Returns the same structure as rules_parser.translate_rules_text():
    {"effects": list, "keywords": set[Keyword], "triggered_abilities": list, "activated_abilities": list}

    Raises LLMParseError on irrecoverable issues.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"Invalid JSON from LLM: {e}") from e

    if not isinstance(data, dict):
        raise LLMParseError("LLM returned non-object JSON")

    result: dict[str, Any] = {
        "effects": [],
        "keywords": set(),
        "triggered_abilities": [],
        "activated_abilities": [],
    }

    # --- Effects ---
    for effect in data.get("effects", []):
        validated = _validate_effect(effect)
        if validated:
            result["effects"].append(validated)

    # --- Keywords ---
    for kw in data.get("keywords", []):
        if isinstance(kw, str):
            kw_lower = kw.lower().replace(" ", "_")
            if kw_lower in KEYWORD_MAP:
                result["keywords"].add(KEYWORD_MAP[kw_lower])

    # --- Triggered abilities ---
    for trig in data.get("triggered_abilities", []):
        if not isinstance(trig, dict):
            continue
        trigger_event = trig.get("trigger")
        if trigger_event not in _VALID_TRIGGER_EVENTS:
            continue
        source = trig.get("source", {"relation": "self"})
        if not isinstance(source, dict):
            source = {"relation": "self"}
        effects = []
        for e in trig.get("effects", []):
            v = _validate_effect(e)
            if v:
                effects.append(v)
        if effects:
            result["triggered_abilities"].append({
                "trigger": trigger_event,
                "source": source,
                "effects": effects,
            })

    # --- Activated abilities ---
    for act in data.get("activated_abilities", []):
        if not isinstance(act, dict):
            continue
        cost = act.get("cost", {})
        if not isinstance(cost, dict):
            cost = {}
        # Normalize sacrifice cost: string → {"types": [string]}
        sac = cost.get("sacrifice")
        if isinstance(sac, str):
            cost = dict(cost)
            cost["sacrifice"] = {"types": [sac]}
        effects = []
        for e in act.get("effects", []):
            v = _validate_effect(e)
            if v:
                effects.append(v)
        if effects:
            result["activated_abilities"].append({
                "cost": cost,
                "effects": effects,
            })

    return result


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class LLMParseError(Exception):
    """Raised when LLM parsing fails irrecoverably."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def translate_rules_text_llm(
    rules_text: str,
    model: str = "mistral:latest",
    ollama_base_url: str | None = None,
    timeout: float = 120.0,
) -> dict:
    """Translate MTG rules text using an LLM via Ollama.

    Returns the same format as rules_parser.translate_rules_text():
    {"effects": list, "keywords": set[Keyword], "triggered_abilities": list, "activated_abilities": list}

    Falls back to the regex parser on any failure.
    """
    if ollama_base_url is None:
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    try:
        raw = _call_ollama(rules_text, model, ollama_base_url, timeout)
        result = _validate_and_normalize(raw)
        # Tag the result so callers know the source
        result["_source"] = "llm"
        result["_model"] = model
        return result
    except Exception as e:
        logger.warning("LLM parse failed (%s), falling back to regex parser", e)
        from mtg_engine.dsl.rules_parser import translate_rules_text
        result = translate_rules_text(rules_text)
        result["_source"] = "regex_fallback"
        return result


def get_available_models(ollama_base_url: str | None = None, timeout: float = 5.0) -> list[dict]:
    """Query Ollama for available models. Returns list of model info dicts."""
    if ollama_base_url is None:
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        resp = requests.get(f"{ollama_base_url}/api/tags", timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Full card DSL generation from natural language
# ---------------------------------------------------------------------------

_GENERATE_CARD_PROMPT = """\
You are an MTG card designer. Given a natural language description of a Magic: The Gathering card, \
generate the complete card definition in the engine's DSL format. Output ONLY the raw DSL text — \
no explanation, no markdown fences, no commentary, no extra text.

""" + _DSL_SPEC + """

## CARD DSL FORMAT

```
card "Card Name" {
    type: <CardType>
    cost: <mana_symbols>
    supertype: Legendary
    subtype: <subtype name>
    p/t: <power> / <toughness>
    loyalty: <number>
    keywords: <keyword>, <keyword>
    effect: <effect_expression>
    when(<event>): <effect_expression>
    when(<event>, <source_filters>): <effect_expression>
    activate(<mana_cost>): <effect_expression>
    activate(<mana_cost>, sacrifice(<type>)): <effect_expression>
    loyalty(<+N or -N>): <effect_expression>
    replace(<event>): <replacement_action>
    enchant: <type>
    equip: <mana_cost>
    rules: "<human-readable rules text>"
}
```

## CARD GENERATION RULES

- Always include `type:` — it is required.
- Include `cost:` for all non-land cards. Each symbol in braces: {2}{R}{R}, not 2RR.
- Include `p/t:` for creatures. Format: `p/t: 3 / 3` (spaces around slash).
- Include `loyalty:` for planeswalkers.
- Use `supertype: Legendary` for legendary/named characters.
- Include a `rules:` line with human-readable rules text in quotes.
- Use explicit DSL properties (keywords, effect, when, activate, loyalty) — do NOT rely on rules: auto-translation.
- For tap abilities: `activate({0}): effect` means the cost is tapping ({T} is implied). Use `activate({2}): effect` for mana-only costs.
- Invent a flavorful name if the user doesn't specify one.
- You can output multiple card blocks if asked.

## EXAMPLES

Input: "a red instant that deals 3 damage to any target for one red mana"
Output:
card "Lightning Bolt" {
    type: Instant
    cost: {R}
    effect: damage(target(any_target), 3)
    rules: "Deal 3 damage to any target."
}

Input: "a 2/3 black vampire with flying, deathtouch, lifelink for 1BB that drains opponents for 2 when it dies"
Output:
card "Nightveil Predator" {
    type: Creature
    cost: {1}{B}{B}
    subtype: Vampire
    p/t: 2 / 3
    keywords: flying, deathtouch, lifelink
    when(dies): lose_life(each_opponent, 2); gain_life(2)
    rules: "Flying, deathtouch, lifelink. When this creature dies, each opponent loses 2 life and you gain 2 life."
}

Input: "a blue instant that returns target nonland permanent to its owner's hand for 1U"
Output:
card "Into the Roil" {
    type: Instant
    cost: {1}{U}
    effect: bounce(target(permanent | !land))
    rules: "Return target nonland permanent to its owner's hand."
}

Input: "a legendary green planeswalker, 4 loyalty, costs 2GG. +1 creates a 1/1 elf token, -3 destroys target artifact, -7 draws 7 cards"
Output:
card "Nissa, Voice of Growth" {
    type: Planeswalker
    cost: {2}{G}{G}
    supertype: Legendary
    subtype: Nissa
    loyalty: 4
    loyalty(+1): create_token("Elf", 1/1)
    loyalty(-3): destroy(target(artifact))
    loyalty(-7): draw(7)
    rules: "+1: Create a 1/1 green Elf creature token. -3: Destroy target artifact. -7: Draw 7 cards."
}

Input: "a white sorcery for 2WW that exiles all attacking creatures"
Output:
card "Settle the Wreckage" {
    type: Sorcery
    cost: {2}{W}{W}
    effect: exile(all(creature, attacking))
    rules: "Exile all attacking creatures."
}

Input: "a 1/1 green elf that taps for green mana, costs G"
Output:
card "Llanowar Elves" {
    type: Creature
    cost: {G}
    subtype: Elf Druid
    p/t: 1 / 1
    activate({0}): add_mana(G)
    rules: "{T}: Add {G}."
}

Input: "a 2/1 red goblin with haste for R that deals 1 damage to each opponent when it attacks"
Output:
card "Goblin Guide" {
    type: Creature
    cost: {R}
    subtype: Goblin
    p/t: 2 / 1
    keywords: haste
    when(attacks): damage(each_opponent, 1)
    rules: "Haste. Whenever this creature attacks, deal 1 damage to each opponent."
}

Input: "an equipment that costs 2, gives +2/+0, equip 1"
Output:
card "Bonesplitter" {
    type: Artifact
    cost: {2}
    subtype: Equipment
    effect: pump(self, +2/+0)
    equip: {1}
    rules: "Equipped creature gets +2/+0. Equip {1}."
}

Input: "an enchantment for 1BB that makes you draw a card at the beginning of your upkeep"
Output:
card "Phyrexian Arena" {
    type: Enchantment
    cost: {1}{B}{B}
    when(begin_upkeep): draw(1)
    rules: "At the beginning of your upkeep, draw a card."
}
"""


import re as _re

# Common LLM vocabulary mistakes → correct DSL function names
_DSL_FIXUPS = [
    # Effect name synonyms the LLM might use instead of the real DSL names
    (r'\breturn\(', 'bounce('),
    (r'\breturn_to_hand\(', 'bounce('),
    (r'\bdeal_damage\(', 'damage('),
    (r'\bdiscard\(', 'sacrifice('),       # only in effect position
    (r'\bcreate\(', 'create_token('),
    (r'\bput_counter\(', 'add_counter('),
    (r'\bplace_counter\(', 'add_counter('),
    (r'\bgrant\(', 'add_keyword('),
    (r'\bgive\(', 'add_keyword('),
    (r'\bcopy\(', 'copy_spell('),
    # Target kind synonyms
    (r'\beach_player\b', 'each_opponent'),
    (r'\ball_opponents\b', 'each_opponent'),
    # Mana symbol formatting (LLM sometimes omits braces)
    (r'\bcost:\s+(\d)([WUBRGC])', r'cost: {\1}{\2}'),
    # "target: creature" → "target(creature)" (LLM sometimes uses colon)
    (r'\btarget:\s*(\w+)', r'target(\1)'),
    # target(self) → self (self is a bare keyword, not wrapped in target())
    (r'\btarget\(self\)', 'self'),
    # target(each_opponent) → each_opponent
    (r'\btarget\(each_opponent\)', 'each_opponent'),
    # Compound type fixups — LLM may combine into one word
    (r'\bnonland_permanent\b', 'permanent | !land'),
    (r'\bnoncreature_permanent\b', 'permanent | !creature'),
    (r'\bnoncreature_spell\b', 'spell | !creature'),
    (r'\bnontoken_creature\b', 'creature | !token'),
    (r'\bnonland\b(?!\s*\|)', 'permanent | !land'),
    (r'\bnoncreature\b(?!\s*\|)', 'permanent | !creature'),
]

# Effects that take ONLY a single target arg — strip any extra args the LLM adds
_SINGLE_TARGET_EFFECTS = frozenset({
    'destroy', 'exile', 'bounce', 'counter', 'tap', 'sacrifice',
})


def _fixup_dsl(dsl: str) -> str:
    """Fix common LLM vocabulary mismatches in generated DSL."""
    for pattern, replacement in _DSL_FIXUPS:
        dsl = _re.sub(pattern, replacement, dsl)

    # Fix single-target effects that got extra args: bounce(target(X), extra) → bounce(target(X))
    for effect in _SINGLE_TARGET_EFFECTS:
        # Match effect(target(...) or all(...) or self or each_opponent), followed by extra junk
        dsl = _re.sub(
            rf'\b{effect}\(((?:target\([^)]*\)|all\([^)]*\)|self|each_opponent))\s*,\s*[^)]*\)',
            rf'{effect}(\1)',
            dsl,
        )

    # Valid effect function names that can appear after "effect:" or after "):"
    _valid_effect_fns = {
        'damage', 'x_damage', 'draw', 'gain_life', 'lose_life',
        'destroy', 'exile', 'bounce', 'counter', 'tap',
        'pump', 'add_keyword', 'add_mana', 'add_counter',
        'mill', 'scry', 'create_token', 'sacrifice',
        'may', 'if_did', 'copy_spell',
    }

    lines = dsl.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Keep blank lines, card/brace structure, and non-effect property lines
        if (not stripped or
            stripped.startswith(('card ', 'type:', 'cost:', 'supertype:', 'subtype:',
                                'p/t:', 'loyalty:', 'rules:',
                                'keywords:', 'enchant:', 'equip:',
                                'adventure ', 'morph:', 'disguise:',
                                'transform:', 'back_face', '//', '{', '}'))):
            cleaned.append(line)
            continue

        # For lines with effects (effect:, when():, activate():, loyalty():, etc.),
        # validate that the effect functions used are in our vocabulary
        if stripped.startswith(('effect:', 'when(', 'activate(', 'loyalty(',
                                'chapter(', 'level(', 'replace(')):
            # Extract function names that appear before '(' in the effect portion
            # Find the effect part (after the last "):" or after "effect:")
            colon_idx = stripped.find(':')
            if colon_idx >= 0:
                effect_part = stripped[colon_idx + 1:].strip()
                # Extract all word( patterns from the effect part
                fn_names = _re.findall(r'\b([a-z_]+)\(', effect_part)
                # Filter out target/all which are valid target constructors
                effect_fns = [fn for fn in fn_names if fn not in ('target', 'all', 'sacrifice')]
                # If any effect function is invalid, drop the line
                if effect_fns and not all(fn in _valid_effect_fns for fn in effect_fns):
                    continue
            cleaned.append(line)
            continue

        # Drop any other unrecognized lines (LLM commentary, etc.)
    return '\n'.join(cleaned)


def generate_card_dsl(
    description: str,
    model: str = "mistral:latest",
    ollama_base_url: str | None = None,
    timeout: float = 180.0,
) -> str:
    """Generate complete card DSL from a natural language description.

    Returns the raw DSL text string. Raises LLMParseError on failure.
    """
    if ollama_base_url is None:
        ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    try:
        resp = requests.post(
            f"{ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _GENERATE_CARD_PROMPT},
                    {"role": "user", "content": description},
                ],
                "stream": False,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]

        # Strip markdown fences if the model wrapped the output
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag)
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return _fixup_dsl(cleaned.strip())
    except requests.RequestException as e:
        raise LLMParseError(f"Ollama request failed: {e}") from e
    except (KeyError, ValueError) as e:
        raise LLMParseError(f"Unexpected Ollama response: {e}") from e


# ---------------------------------------------------------------------------
# Full card text → structured Card dict
# ---------------------------------------------------------------------------

import re as _re_module


def parse_card_text(
    card_text: str,
    model: str = "mistral:latest",
    ollama_base_url: str | None = None,
    timeout: float = 120.0,
) -> dict:
    """Parse a full MTG card text dump into a structured card dict.

    Accepts text like:
        Chain of Vapor
        {U}
        Instant
        Return target nonland permanent to its owner's hand. ...

    Extracts card metadata (name, cost, type, p/t, subtypes) with simple
    parsing and uses the LLM to parse the rules text into structured effects.

    Returns a dict with: name, card_type, cost, rules_text, subtypes,
    power, toughness, loyalty, supertypes, effects, keywords,
    triggered_abilities, activated_abilities, _source, _model.
    """
    lines = [l.strip() for l in card_text.strip().splitlines() if l.strip()]
    if not lines:
        raise LLMParseError("Empty card text")

    # --- Extract card metadata from lines ---
    name = None
    cost = None
    card_type_line = None
    pt_line = None
    loyalty = None
    rules_lines = []

    _CARD_TYPES = {
        "creature", "instant", "sorcery", "enchantment", "artifact",
        "planeswalker", "land", "battle", "kindred",
    }
    _SUPERTYPES = {"legendary", "basic", "snow"}
    _MANA_RE = _re_module.compile(r'^\{[WUBRGCXSP0-9/]+\}(\{[WUBRGCXSP0-9/]+\})*$')
    _PT_RE = _re_module.compile(r'^(\d+|\*)\s*/\s*(\d+|\*)$')

    metadata_done = False
    for line in lines:
        if not metadata_done:
            # Try to identify metadata lines
            if name is None and not _MANA_RE.match(line):
                # First non-mana line is the name
                # But check if it's a type line
                words_lower = [w.lower().rstrip(",") for w in line.split()]
                if any(w in _CARD_TYPES for w in words_lower):
                    # It's a type line, name was probably the previous assignment
                    card_type_line = line
                    if name is None:
                        name = "Unknown"
                else:
                    name = line
                continue
            elif cost is None and _MANA_RE.match(line):
                cost = line
                continue
            elif card_type_line is None:
                words_lower = [w.lower().rstrip(",") for w in line.split()]
                if any(w in _CARD_TYPES for w in words_lower):
                    card_type_line = line
                    continue
                # Check for P/T
                pt_match = _PT_RE.match(line)
                if pt_match:
                    pt_line = line
                    metadata_done = True
                    continue
            elif pt_line is None:
                pt_match = _PT_RE.match(line)
                if pt_match:
                    pt_line = line
                    metadata_done = True
                    continue
                # Check for loyalty
                if _re_module.match(r'^\d+$', line) and card_type_line and 'planeswalker' in card_type_line.lower():
                    loyalty = int(line)
                    metadata_done = True
                    continue
                # Must be start of rules text
                metadata_done = True
                rules_lines.append(line)
                continue
        rules_lines.append(line)

    rules_text = " ".join(rules_lines).strip()

    # --- Parse type line ---
    supertypes = []
    subtypes = []
    card_type = "Instant"

    if card_type_line:
        # Split on em-dash or hyphen for subtypes
        parts = _re_module.split(r'\s*[—\-]\s*', card_type_line, maxsplit=1)
        type_words = parts[0].split()
        if len(parts) > 1:
            subtypes = parts[1].strip().split()

        for word in type_words:
            wl = word.lower().rstrip(",")
            if wl in _SUPERTYPES:
                supertypes.append(word)
            elif wl in _CARD_TYPES:
                card_type = word

    # --- Parse P/T ---
    power = None
    toughness = None
    if pt_line:
        pt_match = _PT_RE.match(pt_line)
        if pt_match:
            p, t = pt_match.group(1), pt_match.group(2)
            power = int(p) if p != '*' else 0
            toughness = int(t) if t != '*' else 0

    # --- Parse rules text with LLM ---
    parsed_rules = {"effects": [], "keywords": set(),
                    "triggered_abilities": [], "activated_abilities": []}
    source = "none"
    model_used = model

    if rules_text:
        parsed_rules = translate_rules_text_llm(
            rules_text, model=model,
            ollama_base_url=ollama_base_url, timeout=timeout,
        )
        source = parsed_rules.pop("_source", "llm")
        model_used = parsed_rules.pop("_model", model)

    return {
        "name": name or "Unknown",
        "card_type": card_type,
        "cost": cost or "",
        "supertypes": supertypes,
        "subtypes": subtypes,
        "power": power,
        "toughness": toughness,
        "loyalty": loyalty,
        "rules_text": rules_text,
        "effects": parsed_rules.get("effects", []),
        "keywords": [kw.name.lower() for kw in parsed_rules.get("keywords", set())],
        "triggered_abilities": parsed_rules.get("triggered_abilities", []),
        "activated_abilities": parsed_rules.get("activated_abilities", []),
        "_source": source,
        "_model": model_used,
    }
