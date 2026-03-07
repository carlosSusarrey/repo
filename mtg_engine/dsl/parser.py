"""Parser that converts DSL text into Card objects."""

from __future__ import annotations

from lark import Lark, Transformer, v_args

from mtg_engine.core.card import Card
from mtg_engine.core.enums import CardType, SuperType
from mtg_engine.core.keywords import Keyword, KEYWORD_MAP
from mtg_engine.core.mana import ManaCost
from mtg_engine.dsl.grammar import CARD_GRAMMAR


CARD_TYPE_MAP = {
    "Creature": CardType.CREATURE,
    "Instant": CardType.INSTANT,
    "Sorcery": CardType.SORCERY,
    "Enchantment": CardType.ENCHANTMENT,
    "Artifact": CardType.ARTIFACT,
    "Planeswalker": CardType.PLANESWALKER,
    "Land": CardType.LAND,
    "Battle": CardType.BATTLE,
    "Kindred": CardType.KINDRED,
}

SUPERTYPE_MAP = {
    "Legendary": SuperType.LEGENDARY,
    "Basic": SuperType.BASIC,
    "Snow": SuperType.SNOW,
}


class CardTransformer(Transformer):
    """Transforms parse tree into Card objects."""

    def start(self, items):
        return list(items)

    def card(self, items):
        name = str(items[0]).strip('"')
        props = items[1]  # card_body returns a dict

        card = Card(name=name, card_type=props.get("type", CardType.CREATURE))

        if "card_types" in props:
            card.card_types = props["card_types"]
            card.card_type = card.card_types[0]

        if "cost" in props:
            card.cost = props["cost"]
        if "supertypes" in props:
            card.supertypes = props["supertypes"]
        if "subtypes" in props:
            card.subtypes = props["subtypes"]
        if "power" in props:
            card.power = props["power"]
        if "toughness" in props:
            card.toughness = props["toughness"]
        if "loyalty" in props:
            card.loyalty = props["loyalty"]
        if "rules_text" in props:
            card.rules_text = props["rules_text"]
        if "effects" in props:
            card.effects = props["effects"]
        if "keywords" in props:
            card.keywords = props["keywords"]
        if "triggered_abilities" in props:
            card.triggered_abilities = props["triggered_abilities"]
        if "activated_abilities" in props:
            card.activated_abilities = props["activated_abilities"]
        if "keyword_params" in props:
            card.keyword_params = props["keyword_params"]

        return card

    def card_body(self, items):
        result = {
            "supertypes": [],
            "subtypes": [],
            "effects": [],
            "keywords": set(),
            "triggered_abilities": [],
            "activated_abilities": [],
            "keyword_params": {},
        }
        for item in items:
            if isinstance(item, dict):
                for key, value in item.items():
                    if key == "supertype":
                        result["supertypes"].append(value)
                    elif key == "subtype":
                        result["subtypes"].append(value)
                    elif key == "effect":
                        result["effects"].append(value)
                    elif key == "keywords":
                        result["keywords"].update(value)
                    elif key == "triggered":
                        result["triggered_abilities"].append(value)
                    elif key == "activated":
                        result["activated_abilities"].append(value)
                    elif key == "keyword_param":
                        kw, val = value
                        result["keyword_params"][kw] = val
                    elif key == "chapter":
                        if "chapters" not in result:
                            result["chapters"] = []
                        result["chapters"].append(value)
                    elif key == "level":
                        if "levels" not in result:
                            result["levels"] = []
                        result["levels"].append(value)
                    elif key == "adventure":
                        result["adventure"] = value
                    elif key == "morph_cost":
                        result["morph_cost"] = value
                    elif key == "disguise_cost":
                        result["disguise_cost"] = value
                    elif key == "transform_condition":
                        result["transform_condition"] = value
                    elif key == "back_face":
                        result["back_face"] = value
                    else:
                        result[key] = value
        return result

    def property(self, items):
        return items[0]

    def type_prop(self, items):
        if len(items) == 1:
            return {"type": CARD_TYPE_MAP[str(items[0])]}
        # Multi-type: type: Artifact Creature
        types = [CARD_TYPE_MAP[str(t)] for t in items]
        return {"type": types[0], "card_types": types}

    def cost_prop(self, items):
        return {"cost": items[0]}

    def supertype_prop(self, items):
        return {"supertype": SUPERTYPE_MAP[str(items[0])]}

    def subtype_prop(self, items):
        return {"subtype": str(items[0]).strip()}

    def power_toughness_prop(self, items):
        return {"power": int(items[0]), "toughness": int(items[1])}

    def loyalty_prop(self, items):
        return {"loyalty": int(items[0])}

    def rules_prop(self, items):
        return {"rules_text": str(items[0]).strip('"')}

    def effect_prop(self, items):
        return {"effect": items[0]}

    def keywords_prop(self, items):
        return {"keywords": items[0]}

    def keyword_list(self, items):
        keywords = set()
        for item in items:
            kw_name = str(item).strip()
            if kw_name in KEYWORD_MAP:
                keywords.add(KEYWORD_MAP[kw_name])
        return keywords

    def source_filter_list(self, items):
        """Build a structured source filter dict from filter keywords."""
        from mtg_engine.core.triggers import _RELATION_KEYWORDS, _CARD_TYPE_KEYWORDS
        result = {}
        for item in items:
            word = str(item).strip()
            if word in _RELATION_KEYWORDS:
                result["relation"] = word
            elif word in _CARD_TYPE_KEYWORDS or word == "permanent":
                result["card_type"] = word
            elif word == "token":
                result["token"] = True
            elif word == "nontoken":
                result["token"] = False
        return result

    def triggered_prop(self, items):
        trigger_event = str(items[0]).strip()
        if len(items) == 3:
            # when(event, filter_words): effect
            source_filter = items[1]  # already a dict from source_filter_list
            effect = items[2]
        else:
            # when(event): effect — defaults to "self"
            source_filter = {"relation": "self"}
            effect = items[1]
        return {"triggered": {
            "trigger": trigger_event,
            "source": source_filter,
            "effects": [effect] if not isinstance(effect, list) else effect,
        }}

    def activated_prop(self, items):
        mana_cost = items[0]
        effect = items[1]
        return {"activated": {
            "cost": {"mana": str(mana_cost), "tap": True},
            "effects": [effect] if not isinstance(effect, list) else effect,
        }}

    def loyalty_ability_prop(self, items):
        loyalty_cost = int(items[0])
        effect = items[1]
        return {"activated": {
            "loyalty_cost": loyalty_cost,
            "is_loyalty": True,
            "effects": [effect] if not isinstance(effect, list) else effect,
        }}

    def enchant_prop(self, items):
        enchant_type = str(items[0]).strip()
        return {"effect": {"type": "enchant", "target_type": enchant_type}}

    def equip_prop(self, items):
        mana_cost = items[0]
        return {"keyword_param": (Keyword.EQUIP, str(mana_cost))}

    # --- Phase 3 grammar handlers ---

    def chapter_prop(self, items):
        chapter_num = int(items[0])
        effect = items[1]
        return {"chapter": {
            "chapter": chapter_num,
            "effects": [effect] if not isinstance(effect, list) else effect,
        }}

    def level_prop(self, items):
        level_num = int(items[0])
        cost = items[1]
        effect = items[2]
        return {"level": {
            "level": level_num,
            "cost": str(cost),
            "effects": [effect] if not isinstance(effect, list) else effect,
        }}

    def adventure_prop(self, items):
        name = str(items[0]).strip('"')
        props = items[1]
        return {"adventure": {
            "name": name,
            "type": props.get("type", CardType.INSTANT),
            "cost": props.get("cost", ManaCost()),
            "effects": props.get("effects", []),
            "rules_text": props.get("rules_text", ""),
        }}

    def adventure_body(self, items):
        result = {"effects": []}
        for item in items:
            if isinstance(item, dict):
                for key, value in item.items():
                    if key == "effect":
                        result["effects"].append(value)
                    else:
                        result[key] = value
        return result

    def adventure_property(self, items):
        return items[0]

    def morph_prop(self, items):
        return {"morph_cost": items[0]}

    def disguise_prop(self, items):
        return {"disguise_cost": items[0]}

    def transform_prop(self, items):
        condition = str(items[0]).strip('"')
        return {"transform_condition": condition}

    def back_face_prop(self, items):
        return {"back_face": items[0]}

    def mana_cost(self, items):
        cost_str = "".join(str(s) for s in items)
        return ManaCost.parse(cost_str)

    def effect(self, items):
        if len(items) == 1:
            return items[0]
        # Multi-effect chain (effect; effect; ...)
        return list(items)

    def effect_single(self, items):
        return items[0]

    def damage_effect(self, items):
        return {"type": "damage", "target": items[0], "amount": int(items[1])}

    def destroy_effect(self, items):
        return {"type": "destroy", "target": items[0]}

    def draw_effect(self, items):
        return {"type": "draw", "amount": int(items[0])}

    def gain_life_effect(self, items):
        return {"type": "gain_life", "amount": int(items[0])}

    def lose_life_effect(self, items):
        return {"type": "lose_life", "target": items[0], "amount": int(items[1])}

    def counter_effect(self, items):
        return {"type": "counter", "target": items[0]}

    def tap_effect(self, items):
        return {"type": "tap", "target": items[0]}

    def create_token_effect(self, items):
        return {
            "type": "create_token",
            "name": str(items[0]).strip('"'),
            "power": int(items[1]),
            "toughness": int(items[2]),
        }

    def pump_effect(self, items):
        return {
            "type": "pump",
            "target": items[0],
            "power": int(items[1]),
            "toughness": int(items[2]),
        }

    def add_keyword_effect(self, items):
        kw_name = str(items[1]).strip()
        return {
            "type": "add_keyword",
            "target": items[0],
            "keyword": kw_name,
        }

    def add_mana_effect(self, items):
        color = str(items[0]).strip()
        return {
            "type": "add_mana",
            "color": color,
        }

    def add_counter_effect(self, items):
        return {
            "type": "add_counter",
            "target": items[0],
            "counter_type": str(items[1]).strip('"'),
            "amount": int(items[2]),
        }

    def mill_effect(self, items):
        return {"type": "mill", "amount": int(items[0])}

    def scry_effect(self, items):
        return {"type": "scry", "amount": int(items[0])}

    def exile_effect(self, items):
        return {"type": "exile", "target": items[0]}

    def bounce_effect(self, items):
        return {"type": "bounce", "target": items[0]}

    def sacrifice_effect(self, items):
        return {"type": "sacrifice", "target": items[0]}

    def x_damage_effect(self, items):
        return {"type": "x_damage", "target": items[0]}

    def target(self, items):
        token = str(items[0])
        if token == "self":
            return {"kind": "self"}
        if token == "each_opponent":
            return {"kind": "each_opponent"}
        return {"kind": "target", "target_type": token}


_parser = Lark(CARD_GRAMMAR, parser="lalr")
_transformer = CardTransformer()


def parse_card(text: str) -> list[Card]:
    """Parse card DSL text and return a list of Card objects."""
    tree = _parser.parse(text)
    return _transformer.transform(tree)


def parse_card_file(filepath: str) -> list[Card]:
    """Parse a .mtg card definition file."""
    with open(filepath) as f:
        return parse_card(f.read())
