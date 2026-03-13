"""Translate natural MTG rules text into structured effect dicts.

When a card defines `rules:` text but no explicit `effect:`, `when():`, or
`keywords:` lines, this module auto-generates the engine's internal
representations from the English rules text.
"""

from __future__ import annotations

import re
from typing import Any

from mtg_engine.core.filters import parse_controller_qualifier, parse_state_qualifier
from mtg_engine.core.keywords import Keyword, KEYWORD_MAP


# ---------------------------------------------------------------------------
# Number words
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _parse_number(text: str) -> int:
    text = text.strip().lower()
    if text.isdigit():
        return int(text)
    return _NUMBER_WORDS.get(text, 1)


# ---------------------------------------------------------------------------
# Keyword detection
# ---------------------------------------------------------------------------

# Natural language keyword name -> DSL keyword name (KEYWORD_MAP key)
_KEYWORD_NATURAL: dict[str, str] = {
    "flying": "flying",
    "first strike": "first_strike",
    "double strike": "double_strike",
    "deathtouch": "deathtouch",
    "trample": "trample",
    "lifelink": "lifelink",
    "vigilance": "vigilance",
    "haste": "haste",
    "hexproof": "hexproof",
    "menace": "menace",
    "defender": "defender",
    "flash": "flash",
    "indestructible": "indestructible",
    "reach": "reach",
    "prowess": "prowess",
    "fear": "fear",
    "intimidate": "intimidate",
    "shroud": "shroud",
    "shadow": "shadow",
    "infect": "infect",
    "wither": "wither",
    "undying": "undying",
    "persist": "persist",
    "flanking": "flanking",
    "horsemanship": "horsemanship",
    "toxic": "toxic",
}


def _try_parse_keywords(sentence: str) -> set[Keyword] | None:
    """If *sentence* is a comma-separated list of keywords, return them."""
    parts = [p.strip().lower() for p in sentence.split(",")]
    keywords: set[Keyword] = set()
    for part in parts:
        if part in _KEYWORD_NATURAL:
            dsl_name = _KEYWORD_NATURAL[part]
            if dsl_name in KEYWORD_MAP:
                keywords.add(KEYWORD_MAP[dsl_name])
        else:
            return None  # not a pure keyword line
    return keywords if keywords else None


# ---------------------------------------------------------------------------
# Centralized qualifier extraction and stripping
# ---------------------------------------------------------------------------

_CONTROLLER_STRIP_PHRASES = [
    "you don't control", "you do not control",
    "an opponent controls", "your opponent controls",
    "your opponents control", "you control",
]

_STATE_WORDS = ("attacking", "blocking", "blocked", "unblocked", "tapped", "untapped")


def _extract_qualifiers(text: str) -> dict[str, str | None]:
    """Extract controller and state qualifiers from natural language text."""
    return {
        "controller": parse_controller_qualifier(text),
        "state": parse_state_qualifier(text),
    }


def _strip_qualifiers(text: str) -> str:
    """Remove qualifier phrases from text so base patterns can match cleanly."""
    result = text.lower()
    for phrase in _CONTROLLER_STRIP_PHRASES:
        result = result.replace(phrase, "")
    for word in _STATE_WORDS:
        result = re.sub(r"\b" + word + r"\b", "", result)
    return re.sub(r"\s+", " ", result).strip()


def _apply_qualifiers(effects: list[dict], qualifiers: dict[str, str | None]) -> None:
    """Inject controller/state qualifiers into target dicts of effects (in-place).

    Only applies to targets with kind "target" or "all" — never to "self" or
    "each_opponent".
    """
    controller = qualifiers.get("controller")
    state = qualifiers.get("state")
    if not controller and not state:
        return
    for effect in effects:
        target = effect.get("target")
        if target is None:
            continue
        kind = target.get("kind")
        if kind not in ("target", "all"):
            continue
        if controller and "controller" not in target:
            target["controller"] = controller
        if state and "state" not in target:
            target["state"] = state


# ---------------------------------------------------------------------------
# Target helpers
# ---------------------------------------------------------------------------

_TARGET_MAP: dict[str, dict[str, str]] = {
    "any target": {"kind": "target", "target_type": "any_target"},
    "target creature": {"kind": "target", "target_type": "creature"},
    "target player": {"kind": "target", "target_type": "player"},
    "target artifact": {"kind": "target", "target_type": "artifact"},
    "target enchantment": {"kind": "target", "target_type": "enchantment"},
    "target permanent": {"kind": "target", "target_type": "permanent"},
    "target planeswalker": {"kind": "target", "target_type": "planeswalker"},
    "target spell": {"kind": "target", "target_type": "spell"},
    "each opponent": {"kind": "each_opponent"},
}


def _parse_target(text: str) -> dict[str, str]:
    """Parse a target phrase, stripping qualifiers to find the base target type."""
    base = _strip_qualifiers(text)
    qualifiers = _extract_qualifiers(text)

    if base in _TARGET_MAP:
        result = dict(_TARGET_MAP[base])
    else:
        m = re.match(r"target\s+(\w+)", base)
        if m:
            result = {"kind": "target", "target_type": m.group(1)}
        else:
            result = {"kind": "target", "target_type": "any_target"}

    if qualifiers["controller"]:
        result["controller"] = qualifiers["controller"]
    if qualifiers["state"]:
        result["state"] = qualifiers["state"]
    return result


def _target_for_type(card_type: str, kind: str = "target") -> dict[str, str]:
    """Build a bare target dict — qualifiers are applied centrally by _apply_qualifiers."""
    return {"kind": kind, "target_type": card_type}


# ---------------------------------------------------------------------------
# Individual effect parsers  (each takes a regex Match, returns list[dict])
#
# Handlers produce BARE targets without qualifiers.  The central
# _parse_effect_text pipeline applies qualifiers after matching.
# ---------------------------------------------------------------------------

_NUM = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"


def _parse_damage_effect(m: re.Match) -> list[dict]:
    amount = _parse_number(m.group(1))
    target = _parse_target(m.group(2))
    return [{"type": "damage", "target": target, "amount": amount}]


def _parse_x_damage_effect(m: re.Match) -> list[dict]:
    target = _parse_target(m.group(1))
    return [{"type": "x_damage", "target": target}]


def _parse_draw_effect(m: re.Match) -> list[dict]:
    amount = _parse_number(m.group(1))
    return [{"type": "draw", "amount": amount}]


def _parse_gain_life_effect(m: re.Match) -> list[dict]:
    amount = _parse_number(m.group(1))
    return [{"type": "gain_life", "amount": amount}]


def _parse_lose_life_each_opp(m: re.Match) -> list[dict]:
    amount = _parse_number(m.group(1))
    return [{"type": "lose_life", "target": {"kind": "each_opponent"}, "amount": amount}]


def _parse_lose_life_target(m: re.Match) -> list[dict]:
    amount = _parse_number(m.group(1))
    return [{"type": "lose_life", "target": _target_for_type("player"), "amount": amount}]


def _parse_pump_effect(m: re.Match) -> list[dict]:
    power = int(m.group(1))
    toughness = int(m.group(2))
    return [{"type": "pump", "target": _target_for_type("creature"), "power": power, "toughness": toughness}]


def _parse_self_pump_effect(m: re.Match) -> list[dict]:
    power = int(m.group(1))
    toughness = int(m.group(2))
    return [{"type": "pump", "target": {"kind": "self"}, "power": power, "toughness": toughness}]


def _parse_destroy_effect(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower()
    return [{"type": "destroy", "target": _target_for_type(card_type)}]


def _parse_exile_effect(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower()
    return [{"type": "exile", "target": _target_for_type(card_type)}]


def _parse_bounce_effect(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower()
    return [{"type": "bounce", "target": _target_for_type(card_type)}]


def _parse_counter_effect(m: re.Match) -> list[dict]:
    return [{"type": "counter", "target": _target_for_type("spell")}]


def _parse_tap_effect(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower()
    return [{"type": "tap", "target": _target_for_type(card_type)}]


def _parse_scry_effect(m: re.Match) -> list[dict]:
    return [{"type": "scry", "amount": int(m.group(1))}]


def _parse_mill_effect(m: re.Match) -> list[dict]:
    return [{"type": "mill", "amount": _parse_number(m.group(1))}]


def _parse_add_mana_effect(m: re.Match) -> list[dict]:
    color = m.group(1).upper()
    return [{"type": "add_mana", "color": color}]


def _parse_create_token_effect(m: re.Match) -> list[dict]:
    count = _parse_number(m.group(1)) if m.group(1) else 1
    power = int(m.group(2))
    toughness = int(m.group(3))
    full = m.group(0)
    name_match = re.search(r"\d+/\d+\s+(.*?)(?:\s+creature)?\s+tokens?", full, re.IGNORECASE)
    name = name_match.group(1).strip() if name_match else "Token"
    tokens = []
    for _ in range(count):
        tokens.append({"type": "create_token", "name": name, "power": power, "toughness": toughness})
    return tokens


def _parse_add_counter_effect(m: re.Match) -> list[dict]:
    count = _parse_number(m.group(1)) if m.group(1) else 1
    counter_type = m.group(2)
    return [{"type": "add_counter", "target": {"kind": "self"}, "counter_type": counter_type, "amount": count}]


def _parse_sacrifice_effect(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower()
    return [{"type": "sacrifice", "target": _target_for_type(card_type)}]


def _parse_self_keyword_effect(m: re.Match) -> list[dict]:
    kw_text = m.group(1).strip().lower()
    dsl_name = _KEYWORD_NATURAL.get(kw_text, kw_text.replace(" ", "_"))
    return [{"type": "add_keyword", "target": {"kind": "self"}, "keyword": dsl_name}]


# ---------------------------------------------------------------------------
# "All" quantifier handlers
# ---------------------------------------------------------------------------

def _parse_destroy_all(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower().rstrip("s")
    return [{"type": "destroy", "target": _target_for_type(card_type, kind="all")}]


def _parse_exile_all(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower().rstrip("s")
    return [{"type": "exile", "target": _target_for_type(card_type, kind="all")}]


def _parse_bounce_all(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower().rstrip("s")
    return [{"type": "bounce", "target": _target_for_type(card_type, kind="all")}]


def _parse_tap_all(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower().rstrip("s")
    return [{"type": "tap", "target": _target_for_type(card_type, kind="all")}]


def _parse_pump_all(m: re.Match) -> list[dict]:
    card_type = m.group(1).lower().rstrip("s")
    power = int(m.group(2))
    toughness = int(m.group(3))
    return [{"type": "pump", "target": _target_for_type(card_type, kind="all"), "power": power, "toughness": toughness}]


# ---------------------------------------------------------------------------
# Pattern tables  (order matters — more specific patterns first)
#
# Regexes match against STRIPPED text (no qualifier words), so they don't
# need _CTRL_SUFFIX or _STATE_PREFIX.  Qualifiers are applied centrally.
# ---------------------------------------------------------------------------

_PERM_TYPES = r"(creature|artifact|enchantment|permanent|planeswalker)"
_PERM_TYPES_PLURAL = r"(creatures?|artifacts?|enchantments?|permanents?|planeswalkers?)"
_BOUNCE_TYPES_PLURAL = r"(creatures?|artifacts?|enchantments?|permanents?)"

_EFFECT_PATTERNS: list[tuple[str, Any]] = [
    # X damage
    (r"deals?\s+X\s+damage\s+to\s+(any target|target creature|target player|each opponent|target permanent|target planeswalker)",
     _parse_x_damage_effect),

    # Numeric damage
    (r"deals?\s+" + _NUM + r"\s+damage\s+to\s+(any target|target creature|target player|each opponent|target permanent|target planeswalker)",
     _parse_damage_effect),

    # Draw
    (r"draws?\s+" + _NUM + r"\s+cards?",
     _parse_draw_effect),

    # Gain life
    (r"gains?\s+" + _NUM + r"\s+life",
     _parse_gain_life_effect),

    # Each opponent loses life
    (r"each\s+opponent\s+loses\s+" + _NUM + r"\s+life",
     _parse_lose_life_each_opp),

    # Target player loses life
    (r"target\s+(?:player|opponent)\s+loses\s+" + _NUM + r"\s+life",
     _parse_lose_life_target),

    # Target creature gets +P/+T
    (r"target\s+creature\s+gets?\s+([+-]\d+)/([+-]\d+)(?:\s+until\s+end\s+of\s+turn)?",
     _parse_pump_effect),

    # Self gets +P/+T
    (r"(?:~|this creature|it|CARDNAME)\s+gets?\s+([+-]\d+)/([+-]\d+)(?:\s+until\s+end\s+of\s+turn)?",
     _parse_self_pump_effect),

    # Destroy target
    (r"destroys?\s+target\s+" + _PERM_TYPES,
     _parse_destroy_effect),

    # Exile target
    (r"exiles?\s+target\s+" + _PERM_TYPES,
     _parse_exile_effect),

    # Bounce target
    (r"returns?\s+target\s+(creature|artifact|enchantment|permanent)\s+to\s+its\s+owner'?s\s+hand",
     _parse_bounce_effect),

    # Counter target spell
    (r"counters?\s+target\s+spell",
     _parse_counter_effect),

    # Tap target
    (r"taps?\s+target\s+(creature|artifact|permanent)",
     _parse_tap_effect),

    # Scry
    (r"scry\s+(\d+)",
     _parse_scry_effect),

    # Mill
    (r"mills?\s+" + _NUM + r"(?:\s+cards?)?",
     _parse_mill_effect),

    # Add mana (with braces)
    (r"adds?\s+\{([WUBRGC])\}",
     _parse_add_mana_effect),

    # Add mana (no braces)
    (r"adds?\s+([WUBRGC])\b",
     _parse_add_mana_effect),

    # Create token
    (r"creates?\s+(?:a\s+|an\s+|(\d+|two|three|four)\s+)?(\d+)/(\d+)(?:\s+\w+)*?\s+(?:creature\s+)?tokens?",
     _parse_create_token_effect),

    # Put counters on self
    (r"puts?\s+(?:a\s+|an\s+|(\d+|two|three|four)\s+)?(\+1/\+1|-1/-1|loyalty|lore)\s+counters?\s+on\s+(?:~|it|this creature|CARDNAME|target creature)",
     _parse_add_counter_effect),

    # Sacrifice
    (r"sacrifices?\s+(?:a|target)\s+(creature|artifact|enchantment|permanent)",
     _parse_sacrifice_effect),

    # Self gains keyword until EOT
    (r"(?:~|this creature|it|CARDNAME)\s+gains?\s+(flying|first strike|double strike|deathtouch|trample|lifelink|vigilance|haste|hexproof|menace|indestructible|reach)(?:\s+until\s+end\s+of\s+turn)?",
     _parse_self_keyword_effect),
]

_ALL_PATTERNS: list[tuple[str, Any]] = [
    # Destroy all
    (r"destroys?\s+all\s+" + _PERM_TYPES_PLURAL,
     _parse_destroy_all),
    # Exile all
    (r"exiles?\s+all\s+" + _PERM_TYPES_PLURAL,
     _parse_exile_all),
    # Return all to hand
    (r"returns?\s+all\s+" + _BOUNCE_TYPES_PLURAL + r"\s+to\s+their\s+owners?'?\s+hands?",
     _parse_bounce_all),
    # Tap all
    (r"taps?\s+all\s+(creatures?|artifacts?|permanents?)",
     _parse_tap_all),
    # All creatures get +N/+N
    (r"all\s+(creatures?|artifacts?|permanents?)\s+get\s+([+-]\d+)/([+-]\d+)(?:\s+until\s+end\s+of\s+turn)?",
     _parse_pump_all),
]


def _parse_effect_text(text: str) -> list[dict]:
    """Parse a natural-language effect clause into effect dicts.

    Qualifier extraction is centralized here:
    1. Extract controller/state qualifiers from raw text
    2. Strip qualifiers to get clean text for pattern matching
    3. Match clean text against patterns
    4. Apply qualifiers to all resulting target dicts
    """
    parts = re.split(r",\s*then\s+|;\s+", text)
    all_effects: list[dict] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Detect "you may" prefix — wrap inner effect in may
        may_match = re.match(r"you\s+may\s+(.*)", part, re.IGNORECASE)
        if may_match:
            inner_effects = _parse_effect_text(may_match.group(1))
            for inner in inner_effects:
                all_effects.append({"type": "may", "inner_effect": inner})
            continue

        # 1+2: Extract qualifiers, then strip for clean matching
        qualifiers = _extract_qualifiers(part)
        clean = _strip_qualifiers(part)

        # 3: Match against patterns (try "all" first, then single-target)
        effects: list[dict] = []
        matched = False
        for pattern, handler in _ALL_PATTERNS:
            m = re.search(pattern, clean, re.IGNORECASE)
            if m:
                effects = handler(m)
                matched = True
                break
        if not matched:
            for pattern, handler in _EFFECT_PATTERNS:
                m = re.search(pattern, clean, re.IGNORECASE)
                if m:
                    effects = handler(m)
                    break

        # 4: Apply qualifiers to all targets in resulting effects
        _apply_qualifiers(effects, qualifiers)
        all_effects.extend(effects)
    return all_effects


# ---------------------------------------------------------------------------
# Triggered ability detection
# ---------------------------------------------------------------------------

_TRIGGER_PATTERNS: list[tuple[str, str]] = [
    (r"[Ww]hen\s+(?:~|this creature|this permanent|CARDNAME|it)\s+enters\s+the\s+battlefield,?\s*(.*)",
     "enters_battlefield"),
    (r"[Ww]henever\s+(?:~|this creature|CARDNAME)\s+attacks,?\s*(.*)",
     "attacks"),
    (r"[Ww]henever\s+(?:~|this creature|CARDNAME)\s+blocks(?:\s+or\s+becomes\s+blocked)?,?\s*(.*)",
     "blocks"),
    (r"[Ww]henever\s+(?:~|this creature|CARDNAME)\s+deals?\s+combat\s+damage\s+to\s+a\s+player,?\s*(.*)",
     "deals_combat_damage_to_player"),
    (r"[Ww]hen\s+(?:~|this creature|CARDNAME)\s+dies,?\s*(.*)",
     "dies"),
    (r"[Ww]henever\s+(?:~|this creature|CARDNAME)\s+dies,?\s*(.*)",
     "dies"),
    (r"[Ww]henever\s+you\s+cast\s+a\s+(?:noncreature\s+)?spell,?\s*(.*)",
     "cast"),
    (r"[Ww]henever\s+a\s+creature\s+enters\s+the\s+battlefield\s+under\s+your\s+control,?\s*(.*)",
     "enters_battlefield"),
    (r"[Ww]henever\s+you\s+gain\s+life,?\s*(.*)",
     "gain_life"),
    (r"[Aa]t\s+the\s+beginning\s+of\s+your\s+upkeep,?\s*(.*)",
     "begin_upkeep"),
    (r"[Aa]t\s+the\s+beginning\s+of\s+(?:your\s+|the\s+)?end\s+step,?\s*(.*)",
     "end_step"),
    (r"[Aa]t\s+the\s+beginning\s+of\s+your\s+draw\s+step,?\s*(.*)",
     "draw_step"),
]


def _try_parse_triggered(sentence: str) -> dict | None:
    """If *sentence* is a triggered ability, return a trigger dict."""
    for pattern, event in _TRIGGER_PATTERNS:
        m = re.match(pattern, sentence)
        if m:
            effect_text = m.group(len(m.groups()))  # last group is the effect
            effects = _parse_effect_text(effect_text)
            if effects:
                return {
                    "trigger": event,
                    "source": {"relation": "self"},
                    "effects": effects,
                }
    return None


# ---------------------------------------------------------------------------
# Activated ability detection
# ---------------------------------------------------------------------------

def _try_parse_activated(sentence: str) -> dict | None:
    """If *sentence* is an activated ability, return an ability dict."""
    # "{T}: effect" or "Tap: effect"
    m = re.match(r"(?:\{T\}|[Tt]ap)\s*:\s*(.*)", sentence)
    if m:
        effects = _parse_effect_text(m.group(1))
        if effects:
            return {
                "cost": {"mana": "{0}", "tap": True},
                "effects": effects,
            }

    # "{mana}, {T}: effect"
    m = re.match(r"(\{[^}]+\}(?:\{[^}]+\})*),\s*\{T\}\s*:\s*(.*)", sentence)
    if m:
        effects = _parse_effect_text(m.group(2))
        if effects:
            return {
                "cost": {"mana": m.group(1), "tap": True},
                "effects": effects,
            }

    # "{mana}: effect" (no tap)
    m = re.match(r"(\{[^}]+\}(?:\{[^}]+\})*)\s*:\s*(.*)", sentence)
    if m:
        effects = _parse_effect_text(m.group(2))
        if effects:
            return {
                "cost": {"mana": m.group(1), "tap": False},
                "effects": effects,
            }

    return None


# ---------------------------------------------------------------------------
# Loyalty ability detection (planeswalkers)
# ---------------------------------------------------------------------------

def _try_parse_loyalty_ability(sentence: str) -> dict | None:
    """If *sentence* is a planeswalker loyalty ability, return an ability dict.

    Matches patterns like: "+1: Draw a card", "−3: Destroy target creature",
    "0: Create a 0/1 white Goat creature token".
    Handles both ASCII minus (-) and unicode minus (−/\\u2212).
    """
    m = re.match(r"^([+\-\u2212]?\d+)\s*:\s*(.*)", sentence)
    if not m:
        return None
    cost_str = m.group(1).replace("\u2212", "-")
    loyalty_cost = int(cost_str)
    effect_text = m.group(2).strip()
    if not effect_text:
        return None
    effects = _parse_effect_text(effect_text)
    if not effects:
        return None
    return {
        "loyalty_cost": loyalty_cost,
        "is_loyalty": True,
        "effects": effects,
    }


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split rules text into individual sentences/clauses."""
    # Split on ". " or "." at end, but not inside mana costs or P/T
    parts = re.split(r"\.\s+|\.\s*$", text.strip())
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def translate_rules_text(rules_text: str) -> dict:
    """Translate MTG rules text into structured effects, triggers, abilities, and keywords.

    Returns a dict with keys: effects, keywords, triggered_abilities, activated_abilities.
    Unrecognized sentences are silently skipped (fail-open).
    """
    result: dict[str, Any] = {
        "effects": [],
        "keywords": set(),
        "triggered_abilities": [],
        "activated_abilities": [],
    }

    sentences = _split_sentences(rules_text)

    for sentence in sentences:
        # 1. Pure keyword line?
        kw = _try_parse_keywords(sentence)
        if kw is not None:
            result["keywords"].update(kw)
            continue

        # 2. Triggered ability?
        triggered = _try_parse_triggered(sentence)
        if triggered is not None:
            result["triggered_abilities"].append(triggered)
            continue

        # 3. Loyalty ability? (planeswalkers: "+1: effect", "−3: effect")
        loyalty = _try_parse_loyalty_ability(sentence)
        if loyalty is not None:
            result["activated_abilities"].append(loyalty)
            continue

        # 4. Activated ability?
        activated = _try_parse_activated(sentence)
        if activated is not None:
            result["activated_abilities"].append(activated)
            continue

        # 5. Standalone effect (for instants/sorceries)
        effects = _parse_effect_text(sentence)
        if effects:
            result["effects"].extend(effects)

    return result
