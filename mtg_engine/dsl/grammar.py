"""Lark grammar definition for the MTG card DSL."""

CARD_GRAMMAR = r"""
start: card+

card: "card" CARD_NAME "{" card_body "}"

card_body: property+

property: type_prop
        | cost_prop
        | supertype_prop
        | subtype_prop
        | power_toughness_prop
        | loyalty_prop
        | rules_prop
        | effect_prop

type_prop: "type:" CARD_TYPE
cost_prop: "cost:" mana_cost
supertype_prop: "supertype:" SUPERTYPE
subtype_prop: "subtype:" IDENTIFIER
power_toughness_prop: "p/t:" NUMBER "/" NUMBER
loyalty_prop: "loyalty:" NUMBER
rules_prop: "rules:" QUOTED_STRING
effect_prop: "effect:" effect

mana_cost: MANA_SYMBOL+

effect: damage_effect
      | destroy_effect
      | draw_effect
      | gain_life_effect
      | lose_life_effect
      | counter_effect
      | tap_effect
      | create_token_effect

damage_effect: "damage(" target "," NUMBER ")"
destroy_effect: "destroy(" target ")"
draw_effect: "draw(" NUMBER ")"
gain_life_effect: "gain_life(" NUMBER ")"
lose_life_effect: "lose_life(" target "," NUMBER ")"
counter_effect: "counter(" target ")"
tap_effect: "tap(" target ")"
create_token_effect: "create_token(" QUOTED_STRING "," NUMBER "/" NUMBER ")"

target: "target(" TARGET_TYPE ")"
      | "self"
      | "each_opponent"
      | "all(" TARGET_TYPE ")"

TARGET_TYPE: "creature" | "player" | "any_target" | "artifact" | "enchantment" | "permanent" | "spell"

CARD_NAME: "\"" /[^"]+/ "\""
QUOTED_STRING: "\"" /[^"]+/ "\""
CARD_TYPE: "Creature" | "Instant" | "Sorcery" | "Enchantment" | "Artifact" | "Planeswalker" | "Land"
SUPERTYPE: "Legendary" | "Basic" | "Snow"
MANA_SYMBOL: "{" /[WUBRGC0-9]+/ "}"
IDENTIFIER: /[a-zA-Z_][a-zA-Z0-9_ ]*/
NUMBER: /[0-9]+/

%import common.WS
%ignore WS
COMMENT: "//" /[^\n]/*
%ignore COMMENT
"""
