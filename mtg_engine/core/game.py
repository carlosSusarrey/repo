"""Game loop and turn structure."""

from __future__ import annotations

import random
from typing import Any

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.combat import (
    CombatState, DamageAssignment, assign_combat_damage,
    get_first_strike_damage, get_regular_damage,
    has_first_strike_creatures, validate_attackers, validate_blockers,
    validate_menace,
)
from mtg_engine.core.enums import CardType, Phase, Step, Zone
from mtg_engine.core.equipment import attach, can_enchant, can_equip
from mtg_engine.core.game_state import GameState
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana_abilities import can_tap_for_mana, tap_for_mana
from mtg_engine.core.planeswalker import activate_loyalty, can_activate_loyalty
from mtg_engine.core.player import Player
from mtg_engine.core.stack import Stack, StackItem
from mtg_engine.core.triggers import TriggerEvent


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

    def _card_lookup(self) -> dict[str, CardInstance]:
        """Build a lookup dict of all cards by instance_id."""
        return {c.instance_id: c for c in self.state.cards}

    # ---- Drawing ----

    def draw_card(self, player_index: int) -> CardInstance | None:
        """Draw a card for a player."""
        library = self.state.get_zone(player_index, Zone.LIBRARY)
        if not library:
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

    # ---- Land & Spells ----

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

        # Trigger landfall
        self.state.triggers.check_triggers(
            TriggerEvent.LAND_ENTERS,
            {"card_id": card.instance_id, "card": card, "player_index": player_index},
            self.state.get_battlefield(),
        )
        # ETB trigger
        self.state.triggers.check_triggers(
            TriggerEvent.ENTERS_BATTLEFIELD,
            {"card_id": card.instance_id, "card": card, "player_index": player_index},
            self.state.get_battlefield(),
        )
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

        # Flash check: non-instant during non-main phase requires flash
        if not card.card.is_instant and not card.has_keyword(Keyword.FLASH):
            if self.state.step != Step.MAIN:
                return False
            if not self.state.stack.is_empty:
                return False

        # Check mana payment
        if not player.mana_pool.can_pay(card.card.cost):
            return False

        # Pay the cost
        player.mana_pool.pay(card.card.cost)

        # Build effects list for the stack item
        effects = list(card.card.effects)
        # Permanents need an enter_battlefield effect so the unified resolver
        # moves them to the battlefield (instead of special-casing in resolve)
        if card.card.card_type not in (CardType.INSTANT, CardType.SORCERY):
            effects.insert(0, {"type": "enter_battlefield"})

        # Put on stack
        card.zone = Zone.STACK
        stack_item = StackItem(
            source_id=card.instance_id,
            controller_index=player_index,
            card_name=card.name,
            effects=effects,
            targets=targets or [],
        )
        self.state.stack.push(stack_item)
        self._log(f"{player.name} casts {card.name}")

        # Fire on-cast triggers (cascade, storm, etc.)
        self.state.triggers.check_triggers(
            TriggerEvent.CAST,
            {"card_id": card.instance_id, "card": card,
             "player_index": player_index},
            self.state.get_battlefield(),
        )
        # Put any pending triggered abilities on the stack
        self.put_triggers_on_stack()

        # Reset priority (action taken)
        self.state.reset_priority()
        return True

    def resolve_top_of_stack(self) -> dict[str, Any] | None:
        """Resolve the top item on the stack.

        All stack items resolve uniformly: iterate effects and resolve each one.
        The stack does not differentiate between spells and abilities.
        After effects resolve, instant/sorcery source cards go to graveyard.
        """
        item = self.state.stack.pop()
        if item is None:
            return None

        result = {"card_name": item.card_name, "effects_resolved": []}

        # Resolve all effects on the stack item
        for effect in item.effects:
            resolved = self._resolve_effect(effect, item)
            result["effects_resolved"].append(resolved)

        # After resolution, instant/sorcery sources go to graveyard
        card = self.state.find_card(item.source_id)
        if card and card.card.card_type in (CardType.INSTANT, CardType.SORCERY):
            card.zone = Zone.GRAVEYARD

        self._log(f"{item.card_name} resolves")
        self.state.check_state_based_actions()
        # Put any pending triggered abilities on the stack
        self.put_triggers_on_stack()
        self.state.reset_priority()
        return result

    def put_triggers_on_stack(self) -> int:
        """Move all pending triggered abilities onto the stack.

        Each pending trigger becomes a StackItem with the trigger's effects.
        Returns the number of triggers placed on the stack.
        """
        count = 0
        while self.state.triggers.has_pending:
            pending = self.state.triggers.pop_pending()
            if pending is None:
                break
            source_card = self.state.find_card(pending.source_card_id)
            trigger_name = f"{source_card.name} trigger" if source_card else "Triggered ability"
            item = StackItem(
                source_id=pending.source_card_id,
                controller_index=pending.controller_index,
                card_name=trigger_name,
                effects=pending.ability.effects,
            )
            self.state.stack.push(item)
            count += 1
        return count

    def _resolve_effect(self, effect: dict[str, Any], item: StackItem) -> dict[str, Any]:
        """Resolve a single effect from a spell or ability."""
        effect_type = effect.get("type", "")
        result = {"type": effect_type, "success": False}

        if effect_type == "damage":
            amount = effect.get("amount", 0)
            source_card = self.state.find_card(item.source_id)
            has_lifelink = source_card and source_card.has_keyword(Keyword.LIFELINK)
            has_deathtouch = source_card and source_card.has_keyword(Keyword.DEATHTOUCH)

            for target_id in item.targets:
                # Try as player
                for i, player in enumerate(self.state.players):
                    if player.name == target_id:
                        player.deal_damage(amount)
                        result["success"] = True
                        self._log(f"{item.card_name} deals {amount} damage to {player.name}")
                        if has_lifelink:
                            self.state.players[item.controller_index].gain_life(amount)
                            self._log(f"Lifelink: {self.state.players[item.controller_index].name} gains {amount} life")

                # Try as creature
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    if has_deathtouch and amount > 0:
                        target_card.damage_marked = target_card.current_toughness or amount
                    else:
                        target_card.damage_marked += amount
                    result["success"] = True
                    self._log(f"{item.card_name} deals {amount} damage to {target_card.name}")
                    if has_lifelink:
                        self.state.players[item.controller_index].gain_life(amount)

        elif effect_type == "destroy":
            for target_id in item.targets:
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    if not target_card.has_keyword(Keyword.INDESTRUCTIBLE):
                        self.state.move_card(target_id, Zone.GRAVEYARD)
                        result["success"] = True
                        self._log(f"{item.card_name} destroys {target_card.name}")
                        if target_card.card.is_creature:
                            self.state.triggers.check_triggers(
                                TriggerEvent.DIES,
                                {"card_id": target_card.instance_id, "card": target_card,
                                 "player_index": target_card.controller_index},
                                self.state.get_battlefield(),
                                self.state.get_zone(target_card.owner_index, Zone.GRAVEYARD),
                            )
                    else:
                        self._log(f"{target_card.name} is indestructible")

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

        elif effect_type == "counter":
            # Counter target spell on the stack
            for target_id in item.targets:
                countered = self.state.stack.remove_by_source(target_id)
                if countered:
                    target_card = self.state.find_card(target_id)
                    if target_card:
                        target_card.zone = Zone.GRAVEYARD
                    result["success"] = True
                    self._log(f"{item.card_name} counters {countered.card_name}")

        elif effect_type == "tap":
            for target_id in item.targets:
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    target_card.tap()
                    result["success"] = True
                    self._log(f"{item.card_name} taps {target_card.name}")

        elif effect_type == "pump":
            power_mod = effect.get("power", 0)
            toughness_mod = effect.get("toughness", 0)
            target_info = effect.get("target", {})
            if target_info.get("kind") == "self":
                source_card = self.state.find_card(item.source_id)
                if source_card and source_card.zone == Zone.BATTLEFIELD:
                    source_card.temp_power_mod += power_mod
                    source_card.temp_toughness_mod += toughness_mod
                    result["success"] = True
            else:
                for target_id in item.targets:
                    target_card = self.state.find_card(target_id)
                    if target_card and target_card.zone == Zone.BATTLEFIELD:
                        target_card.temp_power_mod += power_mod
                        target_card.temp_toughness_mod += toughness_mod
                        result["success"] = True
                        self._log(f"{target_card.name} gets +{power_mod}/+{toughness_mod}")

        elif effect_type == "add_keyword":
            keyword_name = effect.get("keyword", "")
            from mtg_engine.core.keywords import KEYWORD_MAP
            keyword = KEYWORD_MAP.get(keyword_name)
            if keyword:
                target_info = effect.get("target", {})
                if target_info.get("kind") == "self":
                    source_card = self.state.find_card(item.source_id)
                    if source_card:
                        source_card.granted_keywords.add(keyword)
                        result["success"] = True
                else:
                    for target_id in item.targets:
                        target_card = self.state.find_card(target_id)
                        if target_card and target_card.zone == Zone.BATTLEFIELD:
                            target_card.granted_keywords.add(keyword)
                            result["success"] = True

        elif effect_type == "add_mana":
            color_str = effect.get("color", "")
            player = self.state.players[item.controller_index]
            color_map = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
            attr = color_map.get(color_str)
            if attr:
                setattr(player.mana_pool, attr, getattr(player.mana_pool, attr) + 1)
                result["success"] = True
            elif color_str == "C":
                player.mana_pool.colorless += 1
                result["success"] = True

        elif effect_type == "add_counter":
            counter_type = effect.get("counter_type", "+1/+1")
            amount = effect.get("amount", 1)
            target_info = effect.get("target", {})
            if target_info.get("kind") == "self":
                source_card = self.state.find_card(item.source_id)
                if source_card:
                    source_card.counters[counter_type] = source_card.counters.get(counter_type, 0) + amount
                    result["success"] = True
            else:
                for target_id in item.targets:
                    target_card = self.state.find_card(target_id)
                    if target_card and target_card.zone == Zone.BATTLEFIELD:
                        target_card.counters[counter_type] = target_card.counters.get(counter_type, 0) + amount
                        result["success"] = True

        elif effect_type == "mill":
            amount = effect.get("amount", 1)
            player_index = item.controller_index
            # Mill targets opponent by default, but if targets specified use those
            if item.targets:
                for target_id in item.targets:
                    for i, player in enumerate(self.state.players):
                        if player.name == target_id:
                            player_index = i
            library = self.state.get_zone(player_index, Zone.LIBRARY)
            milled = min(amount, len(library))
            for _ in range(milled):
                if library:
                    card = library[0]
                    card.zone = Zone.GRAVEYARD
            result["success"] = True
            result["milled"] = milled

        elif effect_type == "scry":
            amount = effect.get("amount", 1)
            # Scry just marks success; actual top/bottom decisions need player input
            result["success"] = True
            result["scry_amount"] = amount

        elif effect_type == "exile":
            for target_id in item.targets:
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    self.state.move_card(target_id, Zone.EXILE)
                    result["success"] = True
                    self._log(f"{item.card_name} exiles {target_card.name}")

        elif effect_type == "bounce":
            for target_id in item.targets:
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    self.state.move_card(target_id, Zone.HAND)
                    result["success"] = True
                    self._log(f"{item.card_name} returns {target_card.name} to hand")

        elif effect_type == "sacrifice":
            target_info = effect.get("target", {})
            if target_info.get("kind") == "self":
                source_card = self.state.find_card(item.source_id)
                if source_card and source_card.zone == Zone.BATTLEFIELD:
                    self.state.move_card(item.source_id, Zone.GRAVEYARD)
                    result["success"] = True
                    self._log(f"{source_card.name} is sacrificed")
            else:
                for target_id in item.targets:
                    target_card = self.state.find_card(target_id)
                    if target_card and target_card.zone == Zone.BATTLEFIELD:
                        self.state.move_card(target_id, Zone.GRAVEYARD)
                        result["success"] = True
                        self._log(f"{target_card.name} is sacrificed")

        elif effect_type == "create_token":
            token_name = effect.get("name", "Token")
            power = effect.get("power", 1)
            toughness = effect.get("toughness", 1)
            token = self.create_token(
                item.controller_index, token_name, power, toughness
            )
            if token:
                result["success"] = True
                result["token_id"] = token.instance_id

        elif effect_type == "enter_battlefield":
            source_card = self.state.find_card(item.source_id)
            if source_card:
                self.state.move_card(source_card.instance_id, Zone.BATTLEFIELD)
                # Auras attach to their target on resolution
                if "Aura" in source_card.card.subtypes and item.targets:
                    self.attach_aura(source_card.instance_id, item.targets[0])
                # ETB trigger
                self.state.triggers.check_triggers(
                    TriggerEvent.ENTERS_BATTLEFIELD,
                    {"card_id": source_card.instance_id, "card": source_card,
                     "player_index": source_card.controller_index},
                    self.state.get_battlefield(),
                )
                result["success"] = True

        elif effect_type == "x_damage":
            # X damage uses X value from cost (stored in item or defaults to 0)
            x_value = getattr(item, "x_value", 0)
            for target_id in item.targets:
                for i, player in enumerate(self.state.players):
                    if player.name == target_id:
                        player.deal_damage(x_value)
                        result["success"] = True
                target_card = self.state.find_card(target_id)
                if target_card and target_card.zone == Zone.BATTLEFIELD:
                    target_card.damage_marked += x_value
                    result["success"] = True

        return result

    # ---- Token Creation ----

    def create_token(
        self, controller_index: int, name: str, power: int, toughness: int,
        card_type: CardType = CardType.CREATURE,
        keywords: set | None = None,
    ) -> CardInstance:
        """Create a token on the battlefield."""
        from mtg_engine.core.mana import ManaCost
        token_card = Card(
            name=name,
            card_type=card_type,
            cost=ManaCost(),
            power=power,
            toughness=toughness,
            keywords=keywords or set(),
        )
        token_instance = CardInstance(
            card=token_card,
            zone=Zone.BATTLEFIELD,
            owner_index=controller_index,
            controller_index=controller_index,
            summoning_sick=True,
            is_token=True,
        )
        self.state.cards.append(token_instance)
        self._log(f"Token {name} {power}/{toughness} created for {self.state.players[controller_index].name}")

        # ETB trigger
        self.state.triggers.check_triggers(
            TriggerEvent.ENTERS_BATTLEFIELD,
            {"card_id": token_instance.instance_id, "card": token_instance,
             "player_index": controller_index},
            self.state.get_battlefield(),
        )
        return token_instance

    # ---- Combat ----

    def declare_attackers(self, attacker_ids: list[str]) -> list[str]:
        """Declare attackers. Returns list of valid attacker IDs."""
        self.state.combat.clear()
        creatures = self.state.get_battlefield(self.state.active_player_index)
        valid = validate_attackers(creatures, attacker_ids)

        defending_player = self.state.non_active_player_index
        for aid in valid:
            self.state.combat.declare_attacker(aid, defending_player)
            card = self.state.find_card(aid)
            if card:
                if not card.has_keyword(Keyword.VIGILANCE):
                    card.tap()
                self._log(f"{card.name} attacks")
                self.state.triggers.check_triggers(
                    TriggerEvent.ATTACKS,
                    {"card_id": aid, "card": card,
                     "player_index": card.controller_index},
                    self.state.get_battlefield(),
                )

        self.state.reset_priority()
        return valid

    def declare_blockers(self, blocks: dict[str, str]) -> dict[str, str]:
        """Declare blockers. blocks = {blocker_id: attacker_id}. Returns valid blocks."""
        lookup = self._card_lookup()
        attacker_map = {aid: lookup[aid] for aid in self.state.combat.attackers if aid in lookup}
        blocker_candidates = {
            c.instance_id: c
            for c in self.state.get_battlefield(self.state.non_active_player_index)
        }

        valid = validate_blockers(attacker_map, blocker_candidates, blocks, self.state.combat)

        for blocker_id, attacker_id in valid.items():
            self.state.combat.declare_blocker(blocker_id, attacker_id)
            blocker = lookup.get(blocker_id)
            attacker = lookup.get(attacker_id)
            if blocker and attacker:
                self._log(f"{blocker.name} blocks {attacker.name}")

        menace_violations = validate_menace(self.state.combat, attacker_map)
        for aid in menace_violations:
            self.state.combat.was_blocked.discard(aid)
            self.state.combat.blocked_by[aid] = []
            self._log(f"{attacker_map[aid].name} can't be blocked by fewer than 2 creatures (menace)")

        self.state.reset_priority()
        return valid

    def resolve_combat_damage(self) -> list[str]:
        """Resolve combat damage. Returns log of damage events."""
        if not self.state.combat.has_attackers:
            return []

        damage_log = []
        lookup = self._card_lookup()

        has_fs = has_first_strike_creatures(self.state.combat, lookup)

        if has_fs and not self.state.combat.first_strike_dealt:
            assignments = get_first_strike_damage(self.state.combat, lookup)
            damage_log.extend(self._apply_damage(assignments, lookup))
            self.state.combat.first_strike_dealt = True
            self.state.check_state_based_actions()
            return damage_log

        assignments = get_regular_damage(self.state.combat, lookup)
        damage_log.extend(self._apply_damage(assignments, lookup))
        self.state.check_state_based_actions()
        return damage_log

    def _apply_damage(
        self, assignments: list[DamageAssignment], lookup: dict[str, CardInstance]
    ) -> list[str]:
        """Apply damage assignments and return log entries."""
        log_entries = []

        for dmg in assignments:
            if dmg.target_id.startswith("player:"):
                player_idx = int(dmg.target_id.split(":")[1])
                player = self.state.players[player_idx]
                player.deal_damage(dmg.amount)
                source = lookup.get(dmg.source_id)
                source_name = source.name if source else "Unknown"
                log_entries.append(f"{source_name} deals {dmg.amount} combat damage to {player.name}")

                if source:
                    self.state.triggers.check_triggers(
                        TriggerEvent.DEALS_COMBAT_DAMAGE_TO_PLAYER,
                        {"card_id": source.instance_id, "card": source,
                         "player_index": player_idx, "amount": dmg.amount},
                        self.state.get_battlefield(),
                    )
            else:
                target = lookup.get(dmg.target_id)
                source = lookup.get(dmg.source_id)
                if target and target.zone == Zone.BATTLEFIELD:
                    if dmg.has_deathtouch and dmg.amount > 0:
                        target.damage_marked = target.current_toughness or dmg.amount
                    else:
                        target.damage_marked += dmg.amount
                    source_name = source.name if source else "Unknown"
                    log_entries.append(
                        f"{source_name} deals {dmg.amount} combat damage to {target.name}"
                    )

            if dmg.has_lifelink:
                source = lookup.get(dmg.source_id)
                if source:
                    controller = self.state.players[source.controller_index]
                    controller.gain_life(dmg.amount)
                    log_entries.append(f"Lifelink: {controller.name} gains {dmg.amount} life")

        for entry in log_entries:
            self._log(entry)

        return log_entries

    # ---- Turn Structure ----

    def step_untap(self) -> None:
        """Untap step: untap all permanents of active player."""
        for card in self.state.get_battlefield(self.state.active_player_index):
            card.untap()
            card.summoning_sick = False
        self._log(f"Untap step - {self.state.active_player.name}")

    def step_draw(self) -> None:
        """Draw step: active player draws a card."""
        if self.state.turn_number == 1 and self.state.active_player_index == 0:
            self._log("First player skips draw on turn 1")
            return
        self.draw_card(self.state.active_player_index)

    def step_cleanup(self) -> None:
        """Cleanup step: discard to hand size, clear damage, clear end-of-turn effects."""
        player_idx = self.state.active_player_index
        player = self.state.players[player_idx]

        hand = self.state.get_zone(player_idx, Zone.HAND)
        while len(hand) > 7:
            card = hand.pop()
            card.zone = Zone.GRAVEYARD
            self._log(f"{player.name} discards {card.name}")

        for card in self.state.get_battlefield():
            card.damage_marked = 0
            card.clear_end_of_turn()

        self.state.combat.clear()

        for p in self.state.players:
            p.mana_pool.empty()

    def advance_step(self) -> tuple[Phase, Step]:
        """Advance to the next step/phase. Returns the new (phase, step)."""
        current = (self.state.phase, self.state.step)
        idx = TURN_STRUCTURE.index(current)

        if idx + 1 >= len(TURN_STRUCTURE):
            self.advance_turn()
            self.state.phase, self.state.step = TURN_STRUCTURE[0]
        else:
            self.state.phase, self.state.step = TURN_STRUCTURE[idx + 1]

        self.state.reset_priority()
        return (self.state.phase, self.state.step)

    def advance_turn(self) -> None:
        """Move to the next turn."""
        self.step_cleanup()
        self.state.active_player_index = self.state.non_active_player_index
        self.state.priority_player_index = self.state.active_player_index
        self.state.turn_number += 1
        self.state.active_player.reset_for_turn()
        self.state.loyalty_activated_this_turn.clear()
        self.state.continuous_effects.remove_end_of_turn_effects()
        self._log(f"\n--- Turn {self.state.turn_number}: {self.state.active_player.name} ---")

    def run_step(self) -> list[str]:
        """Execute the current step's automatic actions and return log entries."""
        step_log = []
        step = self.state.step

        if step == Step.UNTAP:
            self.step_untap()
        elif step == Step.DRAW:
            self.step_draw()
        elif step == Step.CLEANUP:
            self.step_cleanup()

        sba_log = self.state.check_state_based_actions()
        step_log.extend(sba_log)

        return step_log

    # ---- Mana Abilities ----

    def tap_land_for_mana(self, player_index: int, instance_id: str) -> bool:
        """Tap a land or mana source for mana. Doesn't use the stack."""
        card = self.state.find_card(instance_id)
        if card is None or card.controller_index != player_index:
            return False

        player = self.state.players[player_index]
        color = tap_for_mana(card, player.mana_pool)
        if color is None:
            return False

        self._log(f"{player.name} taps {card.name} for {color.value}")
        return True

    # ---- Equipment / Auras ----

    def equip(self, player_index: int, equipment_id: str, target_id: str) -> bool:
        """Equip an equipment to a target creature.

        CR 301.5: Equip is a sorcery-speed activated ability.
        """
        equipment = self.state.find_card(equipment_id)
        target = self.state.find_card(target_id)
        if equipment is None or target is None:
            return False
        if equipment.controller_index != player_index:
            return False

        if not can_equip(equipment, target):
            return False

        # Check sorcery timing
        if self.state.step != Step.MAIN or not self.state.stack.is_empty:
            return False

        # Check equip cost
        equip_cost = equipment.card.keyword_params.get(Keyword.EQUIP)
        if equip_cost is not None:
            player = self.state.players[player_index]
            from mtg_engine.core.mana import ManaCost
            cost = ManaCost.parse(equip_cost) if isinstance(equip_cost, str) else ManaCost()
            if not player.mana_pool.can_pay(cost):
                return False
            player.mana_pool.pay(cost)

        # Detach from old target if needed
        if equipment.attached_to is not None:
            old_target = self.state.find_card(equipment.attached_to)
            if old_target and equipment.instance_id in old_target.attachments:
                old_target.attachments.remove(equipment.instance_id)

        attach(equipment, target)
        self._log(f"{equipment.name} equipped to {target.name}")
        self.state.reset_priority()
        return True

    def attach_aura(self, aura_id: str, target_id: str) -> bool:
        """Attach an aura to a target permanent (called during resolution)."""
        aura = self.state.find_card(aura_id)
        target = self.state.find_card(target_id)
        if aura is None or target is None:
            return False

        if not can_enchant(aura, target):
            return False

        attach(aura, target)
        self._log(f"{aura.name} enchants {target.name}")
        return True

    # ---- Planeswalker Abilities ----

    def activate_planeswalker(
        self, player_index: int, planeswalker_id: str, ability_index: int,
        targets: list[str] | None = None,
    ) -> bool:
        """Activate a loyalty ability on a planeswalker.

        CR 306.5d: Sorcery speed, once per turn per planeswalker.
        """
        card = self.state.find_card(planeswalker_id)
        if card is None or card.controller_index != player_index:
            return False

        # Sorcery timing
        if self.state.step != Step.MAIN or not self.state.stack.is_empty:
            return False

        result = activate_loyalty(
            card, ability_index, self.state.loyalty_activated_this_turn
        )
        if result is None:
            return False

        # Put ability on stack
        stack_item = StackItem(
            source_id=result["source_id"],
            controller_index=result["controller_index"],
            card_name=f"{result['card_name']} loyalty ability",
            effects=result["effects"],
            targets=targets or [],
        )
        self.state.stack.push(stack_item)
        self._log(f"{card.name} activates loyalty ability {ability_index}")
        self.state.reset_priority()
        return True
