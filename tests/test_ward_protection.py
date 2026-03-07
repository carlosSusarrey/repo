"""Tests for Ward and Protection keyword enforcement."""

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Zone
from mtg_engine.core.keywords import (
    Keyword,
    can_be_blocked_by,
    can_be_damaged_by,
    can_be_enchanted_or_equipped_by,
    can_be_targeted_by_controller,
    can_be_targeted_by_opponent,
    can_block,
    has_ward_cost,
)
from mtg_engine.core.mana import ManaCost, ManaPool


# ---- Ward ----

class TestWardCost:
    def test_no_ward(self):
        assert has_ward_cost(set()) is None

    def test_ward_with_param(self):
        cost = has_ward_cost(
            {Keyword.WARD},
            {Keyword.WARD: "{2}"},
        )
        assert cost == "{2}"

    def test_ward_default_cost(self):
        """Ward with no param defaults to {2}."""
        cost = has_ward_cost({Keyword.WARD})
        assert cost == "{2}"

    def test_ward_does_not_prevent_targeting(self):
        """Ward does NOT prevent targeting — only adds a cost."""
        assert can_be_targeted_by_opponent({Keyword.WARD})


class TestWardInGame:
    def _setup_game(self):
        from mtg_engine.core.game import Game
        deck1 = [Card(name=f"Mountain{i}", card_type=CardType.LAND) for i in range(10)]
        deck2 = [Card(name=f"Mountain{i}", card_type=CardType.LAND) for i in range(10)]
        game = Game(["Alice", "Bob"], [deck1, deck2])
        return game

    def test_ward_requires_extra_mana(self):
        game = self._setup_game()
        # Create a creature with ward {2} for Bob
        ward_creature = Card(
            name="Warded Beast", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{2}{G}"), power=3, toughness=3,
            keywords={Keyword.WARD},
            keyword_params={Keyword.WARD: "{2}"},
        )
        ward_inst = CardInstance(
            card=ward_creature, zone=Zone.BATTLEFIELD,
            owner_index=1, controller_index=1,
        )
        game.state.cards.append(ward_inst)

        # Alice has a bolt (costs {R})
        bolt = Card(
            name="Lightning Bolt", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        bolt_inst = CardInstance(
            card=bolt, zone=Zone.HAND,
            owner_index=0, controller_index=0,
        )
        game.state.cards.append(bolt_inst)

        # Alice has only {R} — can't pay ward {2}
        game.state.players[0].mana_pool.red = 1
        game.state.step = game.state.step  # ensure step is set

        # Set step to allow instant cast
        from mtg_engine.core.enums import Step
        game.state.step = Step.MAIN

        result = game.cast_spell(0, bolt_inst.instance_id, targets=[ward_inst.instance_id])
        # Should fail — can pay bolt but not ward
        assert result is False

    def test_ward_paid_successfully(self):
        game = self._setup_game()
        ward_creature = Card(
            name="Warded Beast", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{2}{G}"), power=3, toughness=3,
            keywords={Keyword.WARD},
            keyword_params={Keyword.WARD: "{1}"},
        )
        ward_inst = CardInstance(
            card=ward_creature, zone=Zone.BATTLEFIELD,
            owner_index=1, controller_index=1,
        )
        game.state.cards.append(ward_inst)

        bolt = Card(
            name="Lightning Bolt", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        )
        bolt_inst = CardInstance(
            card=bolt, zone=Zone.HAND,
            owner_index=0, controller_index=0,
        )
        game.state.cards.append(bolt_inst)

        # Alice has {R} + {1} generic (enough for bolt + ward {1})
        game.state.players[0].mana_pool.red = 2  # 1R for bolt, 1 for ward

        from mtg_engine.core.enums import Step
        game.state.step = Step.MAIN

        result = game.cast_spell(0, bolt_inst.instance_id, targets=[ward_inst.instance_id])
        assert result is True


# ---- Protection ----

class TestProtectionTargeting:
    def test_protection_from_red_blocks_red_spell(self):
        assert not can_be_targeted_by_opponent(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "red"},
            source_colors={Color.RED},
        )

    def test_protection_from_red_allows_green_spell(self):
        assert can_be_targeted_by_opponent(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "red"},
            source_colors={Color.GREEN},
        )

    def test_protection_from_all(self):
        assert not can_be_targeted_by_opponent(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "all"},
            source_colors={Color.WHITE},
        )

    def test_protection_blocks_controller_too(self):
        assert not can_be_targeted_by_controller(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "red"},
            source_colors={Color.RED},
        )

    def test_protection_from_instant(self):
        assert not can_be_targeted_by_opponent(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "instant"},
            source_card_types=[CardType.INSTANT],
        )


class TestProtectionBlocking:
    def test_pro_red_cant_be_blocked_by_red(self):
        result = can_block(
            attacker_keywords={Keyword.PROTECTION},
            blocker_keywords=set(),
            attacker_colors=None,
            blocker_colors={Color.RED},
            attacker_keyword_params={Keyword.PROTECTION: "red"},
        )
        assert not result

    def test_pro_red_can_be_blocked_by_green(self):
        result = can_block(
            attacker_keywords={Keyword.PROTECTION},
            blocker_keywords=set(),
            attacker_colors=None,
            blocker_colors={Color.GREEN},
            attacker_keyword_params={Keyword.PROTECTION: "red"},
        )
        assert result

    def test_pro_creature_cant_be_blocked(self):
        result = can_be_blocked_by(
            attacker_keywords={Keyword.PROTECTION},
            attacker_keyword_params={Keyword.PROTECTION: "creature"},
            blocker_card_types=[CardType.CREATURE],
        )
        assert not result


class TestProtectionDamage:
    def test_pro_red_prevents_red_damage(self):
        assert not can_be_damaged_by(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "red"},
            source_colors={Color.RED},
        )

    def test_pro_red_allows_green_damage(self):
        assert can_be_damaged_by(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "red"},
            source_colors={Color.GREEN},
        )

    def test_no_protection_allows_all(self):
        assert can_be_damaged_by(set())


class TestProtectionEnchantEquip:
    def test_pro_white_cant_be_enchanted_by_white(self):
        assert not can_be_enchanted_or_equipped_by(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "white"},
            source_colors={Color.WHITE},
        )

    def test_pro_white_can_be_equipped_by_colorless(self):
        assert can_be_enchanted_or_equipped_by(
            {Keyword.PROTECTION},
            keyword_params={Keyword.PROTECTION: "white"},
            source_colors=set(),
        )


class TestAuraAttachmentBypassesTargeting:
    """CR 303.4f: An aura put onto the battlefield without being cast
    doesn't target — hexproof/shroud/ward don't prevent attachment."""

    def test_aura_can_attach_to_hexproof_without_cast(self):
        from mtg_engine.core.equipment import can_enchant
        aura_card = Card(
            name="Pacifism", card_type=CardType.ENCHANTMENT,
            cost=ManaCost.parse("{1}{W}"), subtypes=["Aura"],
            effects=[{"type": "enchant", "target_type": "creature"}],
        )
        aura = CardInstance(card=aura_card, zone=Zone.BATTLEFIELD, owner_index=0, controller_index=0)
        creature = CardInstance(
            card=Card(name="Troll", card_type=CardType.CREATURE, power=4, toughness=4,
                      keywords={Keyword.HEXPROOF}),
            zone=Zone.BATTLEFIELD, owner_index=1, controller_index=1,
        )
        # can_enchant only checks type legality, not targeting
        assert can_enchant(aura, creature) is True

    def test_aura_can_attach_to_shroud_without_cast(self):
        from mtg_engine.core.equipment import can_enchant
        aura_card = Card(
            name="Pacifism", card_type=CardType.ENCHANTMENT,
            cost=ManaCost.parse("{1}{W}"), subtypes=["Aura"],
            effects=[{"type": "enchant", "target_type": "creature"}],
        )
        aura = CardInstance(card=aura_card, zone=Zone.BATTLEFIELD, owner_index=0, controller_index=0)
        creature = CardInstance(
            card=Card(name="Troll", card_type=CardType.CREATURE, power=4, toughness=4,
                      keywords={Keyword.SHROUD}),
            zone=Zone.BATTLEFIELD, owner_index=1, controller_index=1,
        )
        assert can_enchant(aura, creature) is True

    def test_aura_falls_off_due_to_protection_sba(self):
        """An aura can momentarily attach to a creature with protection,
        but SBAs immediately move it to the graveyard."""
        from mtg_engine.core.equipment import attach
        from mtg_engine.core.game_state import GameState
        from mtg_engine.core.player import Player

        # White aura on a creature with protection from white
        aura_card = Card(
            name="Pacifism", card_type=CardType.ENCHANTMENT,
            cost=ManaCost.parse("{1}{W}"), subtypes=["Aura"],
            effects=[{"type": "enchant", "target_type": "creature"}],
        )
        aura = CardInstance(card=aura_card, zone=Zone.BATTLEFIELD, owner_index=0, controller_index=0)
        creature = CardInstance(
            card=Card(name="Knight", card_type=CardType.CREATURE, power=2, toughness=2,
                      keywords={Keyword.PROTECTION},
                      keyword_params={Keyword.PROTECTION: "white"},
                      cost=ManaCost.parse("{W}")),
            zone=Zone.BATTLEFIELD, owner_index=1, controller_index=1,
        )

        state = GameState(players=[Player("Alice"), Player("Bob")])
        state.cards.extend([aura, creature])

        # Attach succeeds (no targeting check)
        attach(aura, creature)
        assert aura.attached_to == creature.instance_id

        # SBA detaches and moves aura to graveyard
        actions = state.check_state_based_actions()
        assert aura.zone == Zone.GRAVEYARD
        assert any("protection" in a for a in actions)


class TestManaCostAdd:
    def test_add_mana_costs(self):
        a = ManaCost.parse("{1}{R}")
        b = ManaCost.parse("{2}")
        c = a + b
        assert c.generic == 3
        assert c.red == 1

    def test_add_empty(self):
        a = ManaCost.parse("{R}")
        b = ManaCost()
        c = a + b
        assert c.red == 1
        assert c.generic == 0
