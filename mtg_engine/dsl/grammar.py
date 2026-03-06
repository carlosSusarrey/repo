"""Lark grammar definition for the MTG card DSL.

Phase 3 additions:
- Saga chapters: chapter(N): effect
- Class levels: level(N, cost): effect
- Adventure: adventure "Name" { type: ..., cost: ..., effect: ... }
- Morph/Disguise costs: morph: cost, disguise: cost
- Transform/DFC: transform_condition: "..."
- Hybrid mana: {W/U}, Phyrexian mana: {W/P}, Snow: {S}, X costs: {X}
- Multi-effect chains: effect; effect
"""

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
        | keywords_prop
        | triggered_prop
        | activated_prop
        | loyalty_ability_prop
        | enchant_prop
        | equip_prop
        | chapter_prop
        | level_prop
        | adventure_prop
        | morph_prop
        | disguise_prop
        | transform_prop
        | back_face_prop

type_prop: "type:" CARD_TYPE
cost_prop: "cost:" mana_cost
supertype_prop: "supertype:" SUPERTYPE
subtype_prop: "subtype:" IDENTIFIER
power_toughness_prop: "p/t:" NUMBER "/" NUMBER
loyalty_prop: "loyalty:" NUMBER
rules_prop: "rules:" QUOTED_STRING
effect_prop: "effect:" effect
keywords_prop: "keywords:" keyword_list
triggered_prop: "when(" TRIGGER_EVENT "):" effect
activated_prop: "activate(" mana_cost "):" effect
loyalty_ability_prop: "loyalty(" SIGNED_NUMBER "):" effect
enchant_prop: "enchant:" ENCHANT_TYPE
equip_prop: "equip:" mana_cost
chapter_prop: "chapter(" NUMBER "):" effect
level_prop: "level(" NUMBER "," mana_cost "):" effect
adventure_prop: "adventure" CARD_NAME "{" adventure_body "}"
morph_prop: "morph:" mana_cost
disguise_prop: "disguise:" mana_cost
transform_prop: "transform:" QUOTED_STRING
back_face_prop: "back_face" "{" card_body "}"

adventure_body: adventure_property+
adventure_property: type_prop
                  | cost_prop
                  | effect_prop
                  | rules_prop

keyword_list: KEYWORD_NAME ("," KEYWORD_NAME)*

mana_cost: MANA_SYMBOL+

effect: effect_single (";" effect_single)*

effect_single: damage_effect
      | destroy_effect
      | draw_effect
      | gain_life_effect
      | lose_life_effect
      | counter_effect
      | tap_effect
      | create_token_effect
      | pump_effect
      | add_keyword_effect
      | add_mana_effect
      | add_counter_effect
      | mill_effect
      | scry_effect
      | exile_effect
      | bounce_effect
      | sacrifice_effect
      | x_damage_effect

damage_effect: "damage(" target "," NUMBER ")"
destroy_effect: "destroy(" target ")"
draw_effect: "draw(" NUMBER ")"
gain_life_effect: "gain_life(" NUMBER ")"
lose_life_effect: "lose_life(" target "," NUMBER ")"
counter_effect: "counter(" target ")"
tap_effect: "tap(" target ")"
create_token_effect: "create_token(" QUOTED_STRING "," NUMBER "/" NUMBER ")"
pump_effect: "pump(" target "," SIGNED_NUMBER "/" SIGNED_NUMBER ")"
add_keyword_effect: "add_keyword(" target "," KEYWORD_NAME ")"
add_mana_effect: "add_mana(" MANA_COLOR ")"
add_counter_effect: "add_counter(" target "," QUOTED_STRING "," NUMBER ")"
mill_effect: "mill(" NUMBER ")"
scry_effect: "scry(" NUMBER ")"
exile_effect: "exile(" target ")"
bounce_effect: "bounce(" target ")"
sacrifice_effect: "sacrifice(" target ")"
x_damage_effect: "x_damage(" target ")"

target: "target(" TARGET_TYPE ")"
      | SELF_TARGET
      | EACH_OPPONENT_TARGET
      | "all(" TARGET_TYPE ")"

SELF_TARGET: "self"
EACH_OPPONENT_TARGET: "each_opponent"

TARGET_TYPE: "creature" | "player" | "any_target" | "artifact" | "enchantment" | "permanent" | "spell"
ENCHANT_TYPE: "creature" | "artifact" | "land" | "enchantment" | "permanent" | "player"
MANA_COLOR: "W" | "U" | "B" | "R" | "G" | "C"

CARD_NAME: "\"" /[^"]+/ "\""
QUOTED_STRING: "\"" /[^"]+/ "\""
CARD_TYPE: "Creature" | "Instant" | "Sorcery" | "Enchantment" | "Artifact" | "Planeswalker" | "Land"
SUPERTYPE: "Legendary" | "Basic" | "Snow"
MANA_SYMBOL: "{" /[WUBRGCXSP0-9\/]+/ "}"
IDENTIFIER: /[a-zA-Z_][a-zA-Z0-9_ ]*/
NUMBER: /[0-9]+/
SIGNED_NUMBER: /[+-]?[0-9]+/
KEYWORD_NAME: "flying" | "reach" | "first_strike" | "double_strike" | "deathtouch"
            | "trample" | "lifelink" | "vigilance" | "haste" | "hexproof"
            | "menace" | "defender" | "flash" | "indestructible" | "ward"
            | "protection" | "prowess" | "cycling" | "kicker" | "flashback"
            | "equip" | "fear" | "intimidate" | "shroud" | "shadow"
            | "horsemanship" | "landwalk" | "flanking"
            | "morph" | "disguise" | "transform"
            | "toxic" | "wither" | "infect" | "undying" | "persist"
TRIGGER_EVENT: "enters_battlefield" | "leaves_battlefield" | "dies" | "attacks"
             | "blocks" | "deals_combat_damage_to_player" | "begin_upkeep"
             | "end_step" | "land_enters" | "cast"
             | "transforms" | "level_up"

%import common.WS
%ignore WS
COMMENT: "//" /[^\n]/*
%ignore COMMENT
"""
