"""Core game engine: state, zones, phases, stack, combat, keywords, and rules."""

from mtg_engine.core.enums import Color, CardType, Phase, Step, Zone
from mtg_engine.core.mana import ManaCost, ManaPool, HybridMana, PhyrexianMana
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.player import Player
from mtg_engine.core.game_state import GameState
from mtg_engine.core.stack import Stack, StackItem
from mtg_engine.core.combat import CombatState
from mtg_engine.core.triggers import TriggerEvent, TriggerManager
from mtg_engine.core.game import Game
from mtg_engine.core.replacement_effects import (
    ReplacementEffect, ReplacementEffectManager, ReplacementType,
)
from mtg_engine.core.copy_effects import CopyEffect, CopyEffectManager
from mtg_engine.core.face_down import cast_face_down, turn_face_up, is_face_down
from mtg_engine.core.transform import DoubleFacedCard, transform, is_transformed
from mtg_engine.core.sagas import ChapterAbility, SagaState, setup_saga, add_lore_counter
from mtg_engine.core.adventure import AdventureData, setup_adventure
from mtg_engine.core.poison import (
    add_poison_counters, check_poison_loss, has_infect, has_toxic, has_wither,
)
from mtg_engine.core.commander import (
    CommanderState, get_color_identity, validate_commander, validate_deck,
)
from mtg_engine.core.multiplayer import (
    MultiplayerState, get_next_player, get_apnap_order, setup_multiplayer,
)
from mtg_engine.core.sideboard import Sideboard, create_sideboard, wish, learn
from mtg_engine.core.battle import (
    BattleState, setup_battle, deal_damage_to_battle, is_battle_defeated,
)

__all__ = [
    "Color", "CardType", "Phase", "Step", "Zone",
    "ManaCost", "ManaPool", "HybridMana", "PhyrexianMana",
    "Keyword",
    "Card", "CardInstance",
    "Player",
    "GameState",
    "Stack", "StackItem",
    "CombatState",
    "TriggerEvent", "TriggerManager",
    "Game",
    "ReplacementEffect", "ReplacementEffectManager", "ReplacementType",
    "CopyEffect", "CopyEffectManager",
    "cast_face_down", "turn_face_up", "is_face_down",
    "DoubleFacedCard", "transform", "is_transformed",
    "ChapterAbility", "SagaState", "setup_saga", "add_lore_counter",
    "AdventureData", "setup_adventure",
    "add_poison_counters", "check_poison_loss", "has_infect", "has_toxic", "has_wither",
    "CommanderState", "get_color_identity", "validate_commander", "validate_deck",
    "MultiplayerState", "get_next_player", "get_apnap_order", "setup_multiplayer",
    "Sideboard", "create_sideboard", "wish", "learn",
    "BattleState", "setup_battle", "deal_damage_to_battle", "is_battle_defeated",
]
