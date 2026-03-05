"""Game state management - the central state container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.enums import Phase, Step, Zone
from mtg_engine.core.player import Player
from mtg_engine.core.stack import Stack


@dataclass
class GameState:
    """Complete game state at any point in time."""

    players: list[Player] = field(default_factory=list)
    cards: list[CardInstance] = field(default_factory=list)
    stack: Stack = field(default_factory=Stack)
    active_player_index: int = 0
    priority_player_index: int = 0
    phase: Phase = Phase.BEGINNING
    step: Step = Step.UNTAP
    turn_number: int = 1
    game_over: bool = False
    winner_index: int | None = None

    @property
    def active_player(self) -> Player:
        return self.players[self.active_player_index]

    @property
    def priority_player(self) -> Player:
        return self.players[self.priority_player_index]

    @property
    def non_active_player_index(self) -> int:
        return 1 - self.active_player_index

    def get_zone(self, player_index: int, zone: Zone) -> list[CardInstance]:
        """Get all cards in a specific zone for a player."""
        return [
            c for c in self.cards
            if c.owner_index == player_index and c.zone == zone
        ]

    def get_battlefield(self, player_index: int | None = None) -> list[CardInstance]:
        """Get cards on the battlefield, optionally filtered by controller."""
        if player_index is not None:
            return [
                c for c in self.cards
                if c.zone == Zone.BATTLEFIELD and c.controller_index == player_index
            ]
        return [c for c in self.cards if c.zone == Zone.BATTLEFIELD]

    def find_card(self, instance_id: str) -> CardInstance | None:
        """Find a card instance by its ID."""
        for card in self.cards:
            if card.instance_id == instance_id:
                return card
        return None

    def move_card(self, instance_id: str, to_zone: Zone) -> CardInstance | None:
        """Move a card to a different zone."""
        card = self.find_card(instance_id)
        if card:
            card.zone = to_zone
            if to_zone == Zone.BATTLEFIELD:
                if card.card.is_creature:
                    card.summoning_sick = True
            else:
                # Reset battlefield state when leaving
                card.tapped = False
                card.damage_marked = 0
                card.summoning_sick = False
        return card

    def check_state_based_actions(self) -> list[str]:
        """Check and apply state-based actions. Returns descriptions of actions taken."""
        actions = []

        # Check player life totals
        for i, player in enumerate(self.players):
            if player.life <= 0 and not player.lost:
                player.lost = True
                actions.append(f"{player.name} has lost (life <= 0)")

        # Check creature toughness and lethal damage
        for card in self.get_battlefield():
            if card.card.is_creature:
                if card.current_toughness is not None and card.current_toughness <= 0:
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(f"{card.name} dies (toughness <= 0)")
                elif card.lethal_damage:
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(f"{card.name} dies (lethal damage)")

        # Check for game over
        alive_players = [i for i, p in enumerate(self.players) if not p.lost]
        if len(alive_players) <= 1:
            self.game_over = True
            if alive_players:
                self.winner_index = alive_players[0]

        return actions
