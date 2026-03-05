"""Game loop and turn structure."""

from __future__ import annotations

import random
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Phase, Step, Zone
from mtg_engine.core.game_state import GameState
from mtg_engine.core.player import Player
from mtg_engine.core.stack import Stack, StackItem


# Turn structure: (phase, step) pairs in order
TURN_STRUCTURE = [
    (Phase.BEGINNING, Step.UNTAP),
    (Phase.BEGINNING, Step.UPKEEP),
    (Phase.BEGINNING, Step.DRAW),
    (Phase.PRECOMBAT_MAIN, Step.MAIN),
    (Phase.COMBAT, Step.BEGINNING_OF_COMBAT),
    (Phase.COMBAT, Step.DECLARE_ATTACKERS),
    (Phase.COMBAT, Step.DECLARE_BLOCKERS),
    (Phase.COMBAT, Step.COMBAT_DAMAGE),
    (Phase.COMBAT, Step.END_OF_COMBAT),
    (Phase.POSTCOMBAT_MAIN, Step.MAIN),
    (Phase.ENDING, Step.END),
    (Phase.ENDING, Step.CLEANUP),
]


class Game:
    """Manages the game loop and rule enforcement."""

    def __init__(self, player_names: list[str], decks: list[list[Card]]) -> None:
        if len(player_names) != 2 or len(decks) != 2:
            raise ValueError("Currently supports exactly 2 players")

        self.state = GameState()
        self.log: list[str] = []

        # Create players
        for name in player_names:
            self.state.players.append(Player(name=name))

        # Create card instances from decks
        for player_idx, deck in enumerate(decks):
            for card in deck:
                instance = CardInstance(
                    card=card,
                    zone=Zone.LIBRARY,
                    owner_index=player_idx,
                    controller_index=player_idx,
                )
                self.state.cards.append(instance)

        # Shuffle libraries
        for i in range(len(player_names)):
            self._shuffle_library(i)

    def _log(self, message: str) -> None:
        self.log.append(message)

    def _shuffle_library(self, player_index: int) -> None:
        library = self.state.get_zone(player_index, Zone.LIBRARY)
        random.shuffle(library)

    def draw_card(self, player_index: int) -> CardInstance | None:
        """Draw a card for a player."""
        library = self.state.get_zone(player_index, Zone.LIBRARY)
        if not library:
            # Attempting to draw from empty library = lose
            self.state.players[player_index].lost = True
            self._log(f"{self.state.players[player_index].name} loses (empty library)")
            return None

        card = library[0]
        card.zone = Zone.HAND
        self._log(f"{self.state.players[player_index].name} draws {card.name}")
        return card

    def draw_opening_hands(self, hand_size: int = 7) -> None:
        """Draw opening hands for all players."""
        for player_idx in range(len(self.state.players)):
            for _ in range(hand_size):
                self.draw_card(player_idx)

    def play_land(self, player_index: int, instance_id: str) -> bool:
        """Play a land from hand to battlefield."""
        player = self.state.players[player_index]
        card = self.state.find_card(instance_id)

        if card is None or card.zone != Zone.HAND:
            return False
        if not card.card.is_land:
            return False
        if player.land_plays_remaining <= 0:
            return False
        if player_index != self.state.active_player_index:
            return False

        card.zone = Zone.BATTLEFIELD
        player.land_plays_remaining -= 1
        self._log(f"{player.name} plays {card.name}")
        return True

    def cast_spell(self, player_index: int, instance_id: str,
                   targets: list[str] | None = None) -> bool:
        """Cast a spell - put it on the stack."""
        player = self.state.players[player_index]
        card = self.state.find_card(instance_id)

        if card is None or card.zone != Zone.HAND:
            return False
        if card.card.is_land:
            return False

        # Check mana payment
        if not player.mana_pool.can_pay(card.card.cost):
            return False

        # Pay the cost
        player.mana_pool.pay(card.card.cost)

        # Put on stack
        card.zone = Zone.STACK
        stack_item = StackItem(
            source_id=card.instance_id,
            controller_index=player_index,
            card_name=card.name,
            effects=card.card.effects,
            targets=targets or [],
        )
        self.state.stack.push(stack_item)
        self._log(f"{player.name} casts {card.name}")
        return True

    def resolve_top_of_stack(self) -> dict[str, Any] | None:
        """Resolve the top item on the stack."""
        item = self.state.stack.pop()
        if item is None:
            return None

        card = self.state.find_card(item.source_id)
        result = {"card_name": item.card_name, "effects_resolved": []}

        if card:
            if card.card.card_type in (CardType.INSTANT, CardType.SORCERY):
                # Resolve effects then go to graveyard
                for effect in item.effects:
                    resolved = self._resolve_effect(effect, item)
                    result["effects_resolved"].append(resolved)
                card.zone = Zone.GRAVEYARD
            else:
                # Permanents enter the battlefield
                card.zone = Zone.BATTLEFIELD
                if card.card.is_creature:
                    card.summoning_sick = True

        self._log(f"{item.card_name} resolves")
        self.state.check_state_based_actions()
        return result

    def _resolve_effect(self, effect: dict[str, Any], item: StackItem) -> dict[str, Any]:
        """Resolve a single effect from a spell or ability."""
        effect_type = effect.get("type", "")
        result = {"type": effect_type, "success": False}

        if effect_type == "damage":
            amount = effect.get("amount", 0)
            for target_id in item.targets:
                # Try as player
                for i, player in enumerate(self.state.players):
                    if player.name == target_id:
                        player.deal_damage(amount)
                        result["success"] = True
                        self._log(f"{item.card_name} deals {amount} damage to {player.name}")

                # Try as creature
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    target_card.damage_marked += amount
                    result["success"] = True
                    self._log(f"{item.card_name} deals {amount} damage to {target_card.name}")

        elif effect_type == "destroy":
            for target_id in item.targets:
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    self.state.move_card(target_id, Zone.GRAVEYARD)
                    result["success"] = True
                    self._log(f"{item.card_name} destroys {target_card.name}")

        elif effect_type == "draw":
            amount = effect.get("amount", 1)
            for _ in range(amount):
                self.draw_card(item.controller_index)
            result["success"] = True

        elif effect_type == "gain_life":
            amount = effect.get("amount", 0)
            self.state.players[item.controller_index].gain_life(amount)
            result["success"] = True

        elif effect_type == "lose_life":
            amount = effect.get("amount", 0)
            for target_id in item.targets:
                for i, player in enumerate(self.state.players):
                    if player.name == target_id:
                        player.lose_life(amount)
                        result["success"] = True

        return result

    def step_untap(self) -> None:
        """Untap step: untap all permanents of active player."""
        for card in self.state.get_battlefield(self.state.active_player_index):
            card.untap()
            card.summoning_sick = False
        self._log(f"Untap step - {self.state.active_player.name}")

    def step_draw(self) -> None:
        """Draw step: active player draws a card."""
        # Skip draw on first player's first turn
        if self.state.turn_number == 1 and self.state.active_player_index == 0:
            self._log("First player skips draw on turn 1")
            return
        self.draw_card(self.state.active_player_index)

    def advance_turn(self) -> None:
        """Move to the next turn."""
        # Switch active player
        self.state.active_player_index = self.state.non_active_player_index
        self.state.priority_player_index = self.state.active_player_index
        self.state.turn_number += 1
        self.state.active_player.reset_for_turn()
        self.state.active_player.mana_pool.empty()
        self._log(f"\n--- Turn {self.state.turn_number}: {self.state.active_player.name} ---")
