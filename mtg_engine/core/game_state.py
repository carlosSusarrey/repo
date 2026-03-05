"""Game state management - the central state container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.combat import CombatState
from mtg_engine.core.enums import Phase, Step, Zone, SuperType
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.player import Player
from mtg_engine.core.stack import Stack
from mtg_engine.core.triggers import TriggerManager


@dataclass
class GameState:
    """Complete game state at any point in time."""

    players: list[Player] = field(default_factory=list)
    cards: list[CardInstance] = field(default_factory=list)
    stack: Stack = field(default_factory=Stack)
    combat: CombatState = field(default_factory=CombatState)
    triggers: TriggerManager = field(default_factory=TriggerManager)
    active_player_index: int = 0
    priority_player_index: int = 0
    phase: Phase = Phase.BEGINNING
    step: Step = Step.UNTAP
    turn_number: int = 1
    game_over: bool = False
    winner_index: int | None = None
    # Priority tracking
    players_passed: set[int] = field(default_factory=set)

    @property
    def active_player(self) -> Player:
        return self.players[self.active_player_index]

    @property
    def priority_player(self) -> Player:
        return self.players[self.priority_player_index]

    @property
    def non_active_player_index(self) -> int:
        return 1 - self.active_player_index

    @property
    def all_players_passed(self) -> bool:
        return len(self.players_passed) >= len(self.players)

    def reset_priority(self) -> None:
        """Reset priority to active player (after action or new step)."""
        self.priority_player_index = self.active_player_index
        self.players_passed.clear()

    def pass_priority(self) -> bool:
        """Current priority player passes. Returns True if all have passed."""
        self.players_passed.add(self.priority_player_index)
        if self.all_players_passed:
            return True
        # Move to next player
        self.priority_player_index = (self.priority_player_index + 1) % len(self.players)
        return False

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
                card.granted_keywords.clear()
                card.removed_keywords.clear()
                card.temp_power_mod = 0
                card.temp_toughness_mod = 0
        return card

    def check_state_based_actions(self) -> list[str]:
        """Check and apply state-based actions. Returns descriptions of actions taken."""
        actions = []

        # CR 704.5a: Player with 0 or less life loses
        for i, player in enumerate(self.players):
            if player.life <= 0 and not player.lost:
                player.lost = True
                actions.append(f"{player.name} has lost (life <= 0)")

        # CR 704.5b: Creature with 0 or less toughness goes to graveyard
        # CR 704.5c: Creature with lethal damage goes to graveyard (if not indestructible)
        for card in self.get_battlefield():
            if card.card.is_creature:
                if card.current_toughness is not None and card.current_toughness <= 0:
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(f"{card.name} dies (toughness <= 0)")
                elif card.lethal_damage:
                    if not card.has_keyword(Keyword.INDESTRUCTIBLE):
                        self.move_card(card.instance_id, Zone.GRAVEYARD)
                        actions.append(f"{card.name} dies (lethal damage)")

        # CR 704.5i: Planeswalker with 0 loyalty goes to graveyard
        from mtg_engine.core.enums import CardType
        for card in self.get_battlefield():
            if card.card.card_type == CardType.PLANESWALKER:
                loyalty = card.counters.get("loyalty", card.card.loyalty or 0)
                if loyalty <= 0:
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(f"{card.name} goes to graveyard (0 loyalty)")

        # CR 704.5j: Legend rule
        legendaries: dict[tuple[int, str], list[CardInstance]] = {}
        for card in self.get_battlefield():
            if SuperType.LEGENDARY in card.card.supertypes:
                key = (card.controller_index, card.name)
                if key not in legendaries:
                    legendaries[key] = []
                legendaries[key].append(card)

        for (controller, name), legends in legendaries.items():
            if len(legends) > 1:
                to_remove = legends[:-1]
                for card in to_remove:
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(f"{card.name} goes to graveyard (legend rule)")

        # CR 704.5n: +1/+1 and -1/-1 counters cancel out
        for card in self.get_battlefield():
            plus = card.counters.get("+1/+1", 0)
            minus = card.counters.get("-1/-1", 0)
            if plus > 0 and minus > 0:
                cancel = min(plus, minus)
                card.counters["+1/+1"] -= cancel
                card.counters["-1/-1"] -= cancel
                if card.counters["+1/+1"] == 0:
                    del card.counters["+1/+1"]
                if card.counters["-1/-1"] == 0:
                    del card.counters["-1/-1"]
                actions.append(f"{card.name}: {cancel} +1/+1 and -1/-1 counters cancel")

        # CR 704.5p: Aura not attached to legal object goes to graveyard
        for card in self.get_battlefield():
            if "Aura" in card.card.subtypes and card.attached_to is not None:
                target = self.find_card(card.attached_to)
                if target is None or target.zone != Zone.BATTLEFIELD:
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(f"{card.name} goes to graveyard (no legal target)")

        # Check for game over
        alive_players = [i for i, p in enumerate(self.players) if not p.lost]
        if len(alive_players) <= 1:
            self.game_over = True
            if alive_players:
                self.winner_index = alive_players[0]

        return actions
