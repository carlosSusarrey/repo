"""Parser that converts DSL text into Card objects."""

from __future__ import annotations

from lark import Lark, Transformer, v_args

from mtg_engine.core.card import Card
from mtg_engine.core.enums import CardType, SuperType
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

        return card

    def card_body(self, items):
        result = {"supertypes": [], "subtypes": [], "effects": []}
        for item in items:
            if isinstance(item, dict):
                for key, value in item.items():
                    if key == "supertype":
                        result["supertypes"].append(value)
                    elif key == "subtype":
                        result["subtypes"].append(value)
                    elif key == "effect":
                        result["effects"].append(value)
                    else:
                        result[key] = value
        return result

    def property(self, items):
        return items[0]

    def type_prop(self, items):
        return {"type": CARD_TYPE_MAP[str(items[0])]}

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

    def mana_cost(self, items):
        cost_str = "".join(str(s) for s in items)
        return ManaCost.parse(cost_str)

    def effect(self, items):
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

    def target(self, items):
        return {"kind": "target", "target_type": str(items[0])}

    # Handle literal targets
    def __default_token__(self, token):
        if token == "self":
            return {"kind": "self"}
        if token == "each_opponent":
            return {"kind": "each_opponent"}
        return token


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
