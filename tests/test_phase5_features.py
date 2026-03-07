"""Tests for Phase 5 features: death/LTB triggers, legend rule SBA triggers, target legality."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Step, SuperType, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.stack import StackItem
from mtg_engine.core.triggers import TriggerEvent


def _simple_deck(n=20):
    return [
        Card(name=f"Bear {i}", card_type=CardType.CREATURE,
             cost=ManaCost.parse("{1}{G}"), power=2, toughness=2)
        for i in range(n)
    ]


def _setup_game():
    game = Game(["Alice", "Bob"], [_simple_deck(), _simple_deck()])
    game.draw_opening_hands()
    return game


def _place_on_battlefield(game, card, controller=0, instance_id=None):
    """Place a card directly on the battlefield."""
    inst = CardInstance(
        card=card, zone=Zone.BATTLEFIELD,
        instance_id=instance_id or card.name.lower().replace(" ", "_"),
        owner_index=controller, controller_index=controller,
    )
    game.state.cards.append(inst)
    return inst


# ─── Death Triggers ────────────────────────────────────────────────────────


class TestDeathTriggers:
    """CR 700.4: "Dies" means "is put into a graveyard from the battlefield"."""

    def test_dies_trigger_on_destroy_effect(self):
        """A creature with a dies trigger fires when destroyed by a spell."""
        game = _setup_game()
        game.state.step = Step.MAIN

        # Blood Artist: "when this creature dies, each opponent loses 1 life"
        blood_artist = Card(
            name="Blood Artist", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{B}"), power=0, toughness=1,
            triggered_abilities=[{
                "trigger": "dies",
                "source": "self",
                "effects": [{"type": "lose_life", "amount": 1}],
            }],
        )
        ba_inst = _place_on_battlefield(game, blood_artist, controller=0)

        # Cast a destroy spell targeting Blood Artist
        destroy_spell = Card(
            name="Murder", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{1}{B}{B}"),
            effects=[{"type": "destroy"}],
        )
        spell_inst = CardInstance(
            card=destroy_spell, zone=Zone.STACK,
            instance_id="murder_1", owner_index=1, controller_index=1,
        )
        game.state.cards.append(spell_inst)
        item = StackItem(
            source_id="murder_1", controller_index=1,
            card_name="Murder", effects=[{"type": "destroy"}],
            targets=[ba_inst.instance_id],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        # Blood Artist should be in graveyard
        assert ba_inst.zone == Zone.GRAVEYARD
        # There should be a pending trigger on the stack (put_triggers_on_stack called)
        assert game.state.stack.size >= 1
        top = game.state.stack.peek()
        assert "Blood Artist" in top.card_name

    def test_dies_trigger_on_lethal_damage_sba(self):
        """A creature with a dies trigger fires when killed by lethal damage via SBAs."""
        game = _setup_game()

        # Creature with dies trigger
        doomed = Card(
            name="Doomed Traveler", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{W}"), power=1, toughness=1,
            triggered_abilities=[{
                "trigger": "dies",
                "source": "self",
                "effects": [{"type": "create_token", "name": "Spirit", "power": 1, "toughness": 1}],
            }],
        )
        doomed_inst = _place_on_battlefield(game, doomed, controller=0)
        doomed_inst.damage_marked = 1  # lethal damage

        game.state.check_state_based_actions()

        assert doomed_inst.zone == Zone.GRAVEYARD
        # DIES trigger should be pending
        assert game.state.triggers.has_pending

    def test_dies_trigger_another_creature(self):
        """A 'when another creature dies' trigger fires for a different creature dying."""
        game = _setup_game()

        # Watcher: "when another creature dies, draw a card"
        watcher = Card(
            name="Grim Haruspex", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{2}{B}"), power=3, toughness=2,
            triggered_abilities=[{
                "trigger": "dies",
                "source": {"relation": "another", "card_type": "creature"},
                "effects": [{"type": "draw", "amount": 1}],
            }],
        )
        _place_on_battlefield(game, watcher, controller=0)

        # A different creature that will die
        victim = Card(
            name="Grizzly Bears", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"), power=2, toughness=2,
        )
        victim_inst = _place_on_battlefield(game, victim, controller=0, instance_id="victim_1")
        victim_inst.damage_marked = 2

        game.state.check_state_based_actions()

        assert victim_inst.zone == Zone.GRAVEYARD
        assert game.state.triggers.has_pending
        pending = game.state.triggers.pending
        assert any("Grim Haruspex" in p.source_card_id or
                    p.ability.effects == [{"type": "draw", "amount": 1}]
                    for p in pending)

    def test_dies_trigger_on_sacrifice(self):
        """Sacrificing a creature fires its dies trigger."""
        game = _setup_game()
        game.state.step = Step.MAIN

        creature = Card(
            name="Sakura-Tribe Elder", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"), power=1, toughness=1,
            triggered_abilities=[{
                "trigger": "dies",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 1}],
            }],
        )
        creature_inst = _place_on_battlefield(game, creature, controller=0)

        # Cast a spell that sacrifices the creature
        sac_spell = Card(
            name="Sacrifice Spell", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{B}"),
            effects=[{"type": "sacrifice", "target": {"kind": "self"}}],
        )
        spell_inst = CardInstance(
            card=sac_spell, zone=Zone.STACK,
            instance_id=creature_inst.instance_id,
            owner_index=0, controller_index=0,
        )
        # We need to use the creature as the source so sacrifice self works
        item = StackItem(
            source_id=creature_inst.instance_id,
            controller_index=0, card_name="Sacrifice Spell",
            effects=[{"type": "sacrifice", "target": {"kind": "self"}}],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert creature_inst.zone == Zone.GRAVEYARD
        # The trigger should be on the stack
        assert game.state.stack.size >= 1

    def test_dies_trigger_not_on_exile(self):
        """Exiling a creature does NOT fire dies triggers (it's not going to graveyard)."""
        game = _setup_game()
        game.state.step = Step.MAIN

        creature = Card(
            name="Doomed Creature", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{W}"), power=1, toughness=1,
            triggered_abilities=[{
                "trigger": "dies",
                "source": "self",
                "effects": [{"type": "draw", "amount": 1}],
            }],
        )
        creature_inst = _place_on_battlefield(game, creature, controller=0)

        # Exile the creature
        exile_spell = Card(
            name="Swords to Plowshares", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{W}"), effects=[{"type": "exile"}],
        )
        spell_inst = CardInstance(
            card=exile_spell, zone=Zone.STACK,
            instance_id="swords_1", owner_index=1, controller_index=1,
        )
        game.state.cards.append(spell_inst)
        item = StackItem(
            source_id="swords_1", controller_index=1,
            card_name="Swords to Plowshares",
            effects=[{"type": "exile"}],
            targets=[creature_inst.instance_id],
        )
        game.state.stack.push(item)
        game.resolve_top_of_stack()

        assert creature_inst.zone == Zone.EXILE
        # No dies trigger should have fired — only LTB
        pending = game.state.triggers.pending
        dies_triggers = [p for p in pending if p.ability.trigger.event == TriggerEvent.DIES]
        assert len(dies_triggers) == 0


# ─── Leaves-the-Battlefield Triggers ──────────────────────────────────────


class TestLTBTriggers:
    """CR 603.6c: Leaves-the-battlefield triggers look back to determine if they trigger."""

    def test_ltb_trigger_on_exile(self):
        """A creature with LTB trigger fires when exiled."""
        game = _setup_game()
        game.state.step = Step.MAIN

        creature = Card(
            name="Fiend Hunter", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{W}{W}"), power=1, toughness=3,
            triggered_abilities=[{
                "trigger": "leaves_battlefield",
                "source": "self",
                "effects": [{"type": "draw", "amount": 1}],
            }],
        )
        creature_inst = _place_on_battlefield(game, creature, controller=0)

        # Exile it
        game.state.move_card(creature_inst.instance_id, Zone.EXILE)

        assert creature_inst.zone == Zone.EXILE
        assert game.state.triggers.has_pending
        pending = game.state.triggers.pending
        ltb = [p for p in pending if p.ability.trigger.event == TriggerEvent.LEAVES_BATTLEFIELD]
        assert len(ltb) == 1

    def test_ltb_trigger_on_bounce(self):
        """A creature with LTB trigger fires when bounced to hand."""
        game = _setup_game()
        game.state.step = Step.MAIN

        creature = Card(
            name="Kor Skyfisher", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{W}"), power=2, toughness=3,
            triggered_abilities=[{
                "trigger": "leaves_battlefield",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 2}],
            }],
        )
        creature_inst = _place_on_battlefield(game, creature, controller=0)

        game.state.move_card(creature_inst.instance_id, Zone.HAND)

        assert creature_inst.zone == Zone.HAND
        assert game.state.triggers.has_pending

    def test_ltb_trigger_on_destroy(self):
        """LTB triggers also fire when a creature is destroyed (moves to graveyard)."""
        game = _setup_game()

        creature = Card(
            name="LTB Creature", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{W}"), power=1, toughness=1,
            triggered_abilities=[{
                "trigger": "leaves_battlefield",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 3}],
            }],
        )
        creature_inst = _place_on_battlefield(game, creature, controller=0)

        game.state.move_card(creature_inst.instance_id, Zone.GRAVEYARD)

        assert creature_inst.zone == Zone.GRAVEYARD
        assert game.state.triggers.has_pending
        pending = game.state.triggers.pending
        ltb = [p for p in pending if p.ability.trigger.event == TriggerEvent.LEAVES_BATTLEFIELD]
        assert len(ltb) == 1

    def test_no_ltb_trigger_when_not_leaving_battlefield(self):
        """Moving from hand to graveyard does NOT fire LTB."""
        game = _setup_game()

        creature = Card(
            name="LTB Creature", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{W}"), power=1, toughness=1,
            triggered_abilities=[{
                "trigger": "leaves_battlefield",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 3}],
            }],
        )
        creature_inst = CardInstance(
            card=creature, zone=Zone.HAND,
            instance_id="ltb_hand", owner_index=0, controller_index=0,
        )
        game.state.cards.append(creature_inst)

        game.state.move_card(creature_inst.instance_id, Zone.GRAVEYARD)

        assert creature_inst.zone == Zone.GRAVEYARD
        assert not game.state.triggers.has_pending


# ─── Legend Rule with DIES triggers ───────────────────────────────────────


class TestLegendRuleTriggers:
    """CR 704.5j: Legend rule puts excess legends into graveyard (dies triggers should fire)."""

    def test_legend_rule_fires_dies_trigger(self):
        """When a legendary creature is removed by the legend rule, its dies trigger fires."""
        game = _setup_game()

        legend = Card(
            name="Isamaru", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{W}"), power=2, toughness=2,
            supertypes={SuperType.LEGENDARY},
            triggered_abilities=[{
                "trigger": "dies",
                "source": "self",
                "effects": [{"type": "gain_life", "amount": 5}],
            }],
        )
        legend1 = _place_on_battlefield(game, legend, controller=0, instance_id="isamaru_1")
        legend2 = _place_on_battlefield(game, legend, controller=0, instance_id="isamaru_2")

        game.state.check_state_based_actions()

        # One should be in graveyard (legend rule keeps newest = legend2)
        assert legend1.zone == Zone.GRAVEYARD
        assert legend2.zone == Zone.BATTLEFIELD

        # DIES trigger should fire for the one that went to graveyard
        assert game.state.triggers.has_pending

    def test_legend_rule_keeps_newest(self):
        """Legend rule keeps the most recently added legendary."""
        game = _setup_game()

        legend = Card(
            name="Thalia", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{W}"), power=2, toughness=1,
            supertypes={SuperType.LEGENDARY},
        )
        old = _place_on_battlefield(game, legend, controller=0, instance_id="thalia_old")
        new = _place_on_battlefield(game, legend, controller=0, instance_id="thalia_new")

        game.state.check_state_based_actions()

        assert old.zone == Zone.GRAVEYARD
        assert new.zone == Zone.BATTLEFIELD

    def test_legend_rule_different_controllers(self):
        """Legend rule is per-controller; two players can each have the same legend."""
        game = _setup_game()

        legend = Card(
            name="Isamaru", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{W}"), power=2, toughness=2,
            supertypes={SuperType.LEGENDARY},
        )
        p0 = _place_on_battlefield(game, legend, controller=0, instance_id="isamaru_p0")
        p1 = _place_on_battlefield(game, legend, controller=1, instance_id="isamaru_p1")

        actions = game.state.check_state_based_actions()

        assert p0.zone == Zone.BATTLEFIELD
        assert p1.zone == Zone.BATTLEFIELD
        assert not any("legend rule" in a for a in actions)


# ─── Target Legality on Resolution ────────────────────────────────────────


class TestTargetLegalityOnResolution:
    """CR 608.2b: Spell fizzles if all targets are illegal on resolution."""

    def test_fizzle_when_target_removed(self):
        """A spell fizzles when its target creature is no longer on the battlefield."""
        game = _setup_game()
        game.state.step = Step.MAIN

        # Put a creature on battlefield
        bear = Card(
            name="Target Bear", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"), power=2, toughness=2,
        )
        bear_inst = _place_on_battlefield(game, bear, controller=1, instance_id="target_bear")

        # Put a destroy spell targeting the bear on the stack
        bolt = Card(
            name="Lightning Bolt", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        bolt_inst = CardInstance(
            card=bolt, zone=Zone.STACK,
            instance_id="bolt_1", owner_index=0, controller_index=0,
        )
        game.state.cards.append(bolt_inst)
        item = StackItem(
            source_id="bolt_1", controller_index=0,
            card_name="Lightning Bolt",
            effects=[{"type": "damage", "amount": 3}],
            targets=[bear_inst.instance_id],
        )
        game.state.stack.push(item)

        # Remove the target before resolution (simulating another spell resolving first)
        game.state.move_card(bear_inst.instance_id, Zone.GRAVEYARD)
        game.state.triggers.clear_pending()  # clear LTB triggers for cleanliness

        result = game.resolve_top_of_stack()

        assert result["fizzled"] is True
        assert "fizzles" in game.log[-1] or any("fizzles" in l for l in game.log)
        # Bolt should go to graveyard
        assert bolt_inst.zone == Zone.GRAVEYARD

    def test_resolves_with_some_legal_targets(self):
        """A spell resolves if at least one target is still legal."""
        game = _setup_game()
        game.state.step = Step.MAIN

        bear1 = Card(name="Bear A", card_type=CardType.CREATURE,
                     cost=ManaCost.parse("{1}{G}"), power=2, toughness=2)
        bear2 = Card(name="Bear B", card_type=CardType.CREATURE,
                     cost=ManaCost.parse("{1}{G}"), power=2, toughness=2)
        inst1 = _place_on_battlefield(game, bear1, controller=1, instance_id="bear_a")
        inst2 = _place_on_battlefield(game, bear2, controller=1, instance_id="bear_b")

        # Multi-target damage spell
        spell = Card(
            name="Multi Bolt", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        spell_inst = CardInstance(
            card=spell, zone=Zone.STACK,
            instance_id="multi_bolt", owner_index=0, controller_index=0,
        )
        game.state.cards.append(spell_inst)
        item = StackItem(
            source_id="multi_bolt", controller_index=0,
            card_name="Multi Bolt",
            effects=[{"type": "damage", "amount": 3}],
            targets=["bear_a", "bear_b"],
        )
        game.state.stack.push(item)

        # Remove one target
        game.state.move_card("bear_a", Zone.GRAVEYARD)
        game.state.triggers.clear_pending()

        result = game.resolve_top_of_stack()

        # Should NOT fizzle — bear_b is still legal
        assert "fizzled" not in result
        # bear_b took 3 damage (lethal for 2 toughness), SBAs moved it to graveyard
        assert inst2.zone == Zone.GRAVEYARD

    def test_player_target_stays_legal(self):
        """Player targets remain legal as long as the player hasn't lost."""
        game = _setup_game()
        game.state.step = Step.MAIN

        bolt = Card(
            name="Lava Spike", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        bolt_inst = CardInstance(
            card=bolt, zone=Zone.STACK,
            instance_id="lava_spike", owner_index=0, controller_index=0,
        )
        game.state.cards.append(bolt_inst)
        item = StackItem(
            source_id="lava_spike", controller_index=0,
            card_name="Lava Spike",
            effects=[{"type": "damage", "amount": 3}],
            targets=["Bob"],
        )
        game.state.stack.push(item)

        result = game.resolve_top_of_stack()

        assert "fizzled" not in result
        assert game.state.players[1].life == 17

    def test_fizzle_player_target_lost(self):
        """A spell targeting a player who has lost fizzles."""
        game = _setup_game()
        game.state.step = Step.MAIN

        game.state.players[1].lost = True

        bolt = Card(
            name="Lava Spike", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        bolt_inst = CardInstance(
            card=bolt, zone=Zone.STACK,
            instance_id="lava_spike2", owner_index=0, controller_index=0,
        )
        game.state.cards.append(bolt_inst)
        item = StackItem(
            source_id="lava_spike2", controller_index=0,
            card_name="Lava Spike",
            effects=[{"type": "damage", "amount": 3}],
            targets=["Bob"],
        )
        game.state.stack.push(item)

        result = game.resolve_top_of_stack()

        assert result["fizzled"] is True

    def test_no_fizzle_without_targets(self):
        """Spells without targets always resolve (e.g., Divination)."""
        game = _setup_game()
        game.state.step = Step.MAIN

        divination = Card(
            name="Divination", card_type=CardType.SORCERY,
            cost=ManaCost.parse("{2}{U}"),
            effects=[{"type": "draw", "amount": 2}],
        )
        div_inst = CardInstance(
            card=divination, zone=Zone.STACK,
            instance_id="divination_1", owner_index=0, controller_index=0,
        )
        game.state.cards.append(div_inst)
        item = StackItem(
            source_id="divination_1", controller_index=0,
            card_name="Divination",
            effects=[{"type": "draw", "amount": 2}],
        )
        game.state.stack.push(item)

        hand_before = len(game.state.get_zone(0, Zone.HAND))
        result = game.resolve_top_of_stack()

        assert "fizzled" not in result
        hand_after = len(game.state.get_zone(0, Zone.HAND))
        assert hand_after == hand_before + 2
