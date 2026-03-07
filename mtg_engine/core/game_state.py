"""Game state management - the central state container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtg_engine.core.card import CardInstance
from mtg_engine.core.combat import CombatState
from mtg_engine.core.continuous_effects import ContinuousEffectManager
from mtg_engine.core.enums import Phase, Step, Zone, SuperType, CardType
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
    continuous_effects: ContinuousEffectManager = field(
        default_factory=ContinuousEffectManager
    )
    active_player_index: int = 0
    priority_player_index: int = 0
    phase: Phase = Phase.BEGINNING
    step: Step = Step.UNTAP
    turn_number: int = 1
    game_over: bool = False
    winner_index: int | None = None
    # Priority tracking
    players_passed: set[int] = field(default_factory=set)
    # Planeswalker loyalty tracking (IDs that activated this turn)
    loyalty_activated_this_turn: set[str] = field(default_factory=set)

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
            old_zone = card.zone
            card.zone = to_zone
            if to_zone == Zone.BATTLEFIELD:
                if card.card.is_creature:
                    card.summoning_sick = True
                # Initialize planeswalker loyalty
                if card.card.card_type == CardType.PLANESWALKER:
                    from mtg_engine.core.planeswalker import initialize_loyalty
                    initialize_loyalty(card)
            else:
                # Reset battlefield state when leaving
                card.tapped = False
                card.damage_marked = 0
                card.summoning_sick = False
                card.granted_keywords.clear()
                card.removed_keywords.clear()
                card.temp_power_mod = 0
                card.temp_toughness_mod = 0
                # Handle attachments leaving battlefield
                if old_zone == Zone.BATTLEFIELD:
                    self._handle_leaving_battlefield(card)
                    # Remove continuous effects from this source
                    self.continuous_effects.remove_effects_from(instance_id)
        return card

    def _handle_leaving_battlefield(self, card: CardInstance) -> None:
        """Handle a permanent leaving the battlefield."""
        # Detach from anything it was attached to
        if card.attached_to is not None:
            target = self.find_card(card.attached_to)
            if target and card.instance_id in target.attachments:
                target.attachments.remove(card.instance_id)
            card.attached_to = None

        # Handle things attached to this card
        for attachment_id in list(card.attachments):
            attachment = self.find_card(attachment_id)
            if attachment:
                is_equipment = (
                    attachment.card.card_type == CardType.ARTIFACT
                    and "Equipment" in attachment.card.subtypes
                )
                if is_equipment:
                    # Equipment stays on battlefield, just unattached
                    attachment.attached_to = None
                # Auras will be handled by SBA (no legal target)
        card.attachments.clear()

    def check_state_based_actions(self) -> list[str]:
        """Check and apply state-based actions. Returns descriptions of actions taken."""
        actions = []

        # CR 704.5a: Player with 0 or less life loses
        for i, player in enumerate(self.players):
            if player.life <= 0 and not player.lost:
                player.lost = True
                actions.append(f"{player.name} has lost (life <= 0)")

        # CR 704.5c: Player with 10+ poison counters loses
        for i, player in enumerate(self.players):
            if player.poison_counters >= 10 and not player.lost:
                player.lost = True
                actions.append(f"{player.name} has lost (10+ poison counters)")

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

        # CR 310.7 / CR 704.5s: Battle with 0 defense counters is exiled
        for card in self.get_battlefield():
            if card.card.card_type == CardType.BATTLE:
                defense = card.counters.get("defense", 0)
                if defense <= 0:
                    self.move_card(card.instance_id, Zone.EXILE)
                    actions.append(f"{card.name} exiled (0 defense counters)")

        # CR 704.5d: Tokens not on the battlefield cease to exist
        tokens_to_remove = [
            card for card in self.cards
            if card.is_token and card.zone != Zone.BATTLEFIELD
        ]
        for token in tokens_to_remove:
            self.cards.remove(token)
            actions.append(f"{token.name} token ceases to exist")

        # CR 704.5m: Aura not attached to legal object goes to graveyard
        # This includes auras whose enchanted permanent has protection from the aura
        from mtg_engine.core.keywords import can_be_enchanted_or_equipped_by
        for card in self.get_battlefield():
            if "Aura" in card.card.subtypes and card.attached_to is not None:
                target = self.find_card(card.attached_to)
                if target is None or target.zone != Zone.BATTLEFIELD:
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(f"{card.name} goes to graveyard (no legal target)")
                elif not can_be_enchanted_or_equipped_by(
                    target.keywords,
                    keyword_params=target.card.keyword_params,
                    source_colors=card.card.colors,
                    source_card_types=card.card.card_types,
                ):
                    from mtg_engine.core.equipment import detach
                    detach(card, target)
                    self.move_card(card.instance_id, Zone.GRAVEYARD)
                    actions.append(
                        f"{card.name} goes to graveyard (protection makes attachment illegal)"
                    )

        # Check for game over
        alive_players = [i for i, p in enumerate(self.players) if not p.lost]
        if len(alive_players) <= 1:
            self.game_over = True
            if alive_players:
                self.winner_index = alive_players[0]

        return actions
