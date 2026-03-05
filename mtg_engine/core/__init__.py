"""Core game engine: state, zones, phases, stack, and rules."""

from mtg_engine.core.enums import Color, CardType, Phase, Step, Zone
from mtg_engine.core.mana import ManaCost, ManaPool
from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.player import Player
from mtg_engine.core.game_state import GameState
from mtg_engine.core.stack import Stack, StackItem
from mtg_engine.core.game import Game

__all__ = [
    "Color", "CardType", "Phase", "Step", "Zone",
    "ManaCost", "ManaPool",
    "Card", "CardInstance",
    "Player",
    "GameState",
    "Stack", "StackItem",
    "Game",
]
