"""Tests for the card DSL parser."""

from mtg_engine.core.enums import CardType
from mtg_engine.core.keywords import Keyword
from mtg_engine.dsl import parse_card


class TestDSLParser:
    def test_parse_simple_creature(self):
        dsl = '''
        card "Grizzly Bears" {
            type: Creature
            cost: {1}{G}
            subtype: Bear
            p/t: 2 / 2
        }
        '''
        cards = parse_card(dsl)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Grizzly Bears"
        assert card.card_type == CardType.CREATURE
        assert card.power == 2
        assert card.toughness == 2

    def test_parse_instant_with_effect(self):
        dsl = '''
        card "Lightning Bolt" {
            type: Instant
            cost: {R}
            effect: damage(target(any_target), 3)
        }
        '''
        cards = parse_card(dsl)
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Lightning Bolt"
        assert card.card_type == CardType.INSTANT
        assert len(card.effects) == 1
        assert card.effects[0]["type"] == "damage"
        assert card.effects[0]["amount"] == 3

    def test_parse_multiple_cards(self):
        dsl = '''
        card "Mountain" {
            type: Land
        }
        card "Forest" {
            type: Land
        }
        '''
        cards = parse_card(dsl)
        assert len(cards) == 2

    def test_parse_draw_effect(self):
        dsl = '''
        card "Ancestral Recall" {
            type: Instant
            cost: {U}
            effect: draw(3)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["type"] == "draw"
        assert card.effects[0]["amount"] == 3

    def test_parse_gain_life_effect(self):
        dsl = '''
        card "Healing Salve" {
            type: Instant
            cost: {W}
            effect: gain_life(3)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["type"] == "gain_life"
        assert card.effects[0]["amount"] == 3

    def test_parse_keywords(self):
        dsl = '''
        card "Serra Angel" {
            type: Creature
            cost: {3}{W}{W}
            p/t: 4 / 4
            keywords: flying, vigilance
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.FLYING in card.keywords
        assert Keyword.VIGILANCE in card.keywords

    def test_parse_many_keywords(self):
        dsl = '''
        card "Vampire Nighthawk" {
            type: Creature
            cost: {1}{B}{B}
            p/t: 2 / 3
            keywords: flying, deathtouch, lifelink
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.FLYING in card.keywords
        assert Keyword.DEATHTOUCH in card.keywords
        assert Keyword.LIFELINK in card.keywords
        assert len(card.keywords) == 3

    def test_parse_triggered_ability(self):
        dsl = '''
        card "Wall of Omens" {
            type: Creature
            cost: {1}{W}
            p/t: 0 / 4
            keywords: defender
            when(enters_battlefield): draw(1)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.DEFENDER in card.keywords
        assert len(card.triggered_abilities) == 1
        trigger = card.triggered_abilities[0]
        assert trigger["trigger"] == "enters_battlefield"
        assert trigger["effects"][0]["type"] == "draw"

    def test_parse_pump_effect(self):
        dsl = '''
        card "Giant Growth" {
            type: Instant
            cost: {G}
            effect: pump(target(creature), +3 / +3)
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert card.effects[0]["type"] == "pump"
        assert card.effects[0]["power"] == 3
        assert card.effects[0]["toughness"] == 3

    def test_parse_flash(self):
        dsl = '''
        card "Ambush Viper" {
            type: Creature
            cost: {1}{G}
            p/t: 2 / 1
            keywords: flash, deathtouch
        }
        '''
        cards = parse_card(dsl)
        card = cards[0]
        assert Keyword.FLASH in card.keywords
        assert Keyword.DEATHTOUCH in card.keywords

    def test_parse_full_sample_file(self):
        """Parse the full sample.mtg file to ensure it's valid."""
        from mtg_engine.dsl import parse_card_file
        cards = parse_card_file("cards/sample.mtg")
        assert len(cards) >= 10
        # Check Serra Angel has keywords
        serra = [c for c in cards if c.name == "Serra Angel"][0]
        assert Keyword.FLYING in serra.keywords
        assert Keyword.VIGILANCE in serra.keywords


class TestTypeExpressions:
    """Tests for the new type expression system with | (union) and ! (negation)."""

    def test_simple_type(self):
        cards = parse_card('''
        card "Test" {
            type: Instant
            cost: {R}
            effect: damage(target(creature), 3)
        }
        ''')
        target = cards[0].effects[0]["target"]
        assert target["kind"] == "target"
        assert target["types"] == ["creature"]
        assert "exclude_types" not in target

    def test_negation_nonland_permanent(self):
        cards = parse_card('''
        card "Test" {
            type: Instant
            cost: {1}{U}
            effect: bounce(target(permanent | !land))
        }
        ''')
        target = cards[0].effects[0]["target"]
        assert target["types"] == ["permanent"]
        assert target["exclude_types"] == ["land"]

    def test_union_creature_or_planeswalker(self):
        cards = parse_card('''
        card "Test" {
            type: Sorcery
            cost: {2}{B}
            effect: destroy(target(creature | planeswalker))
        }
        ''')
        target = cards[0].effects[0]["target"]
        assert target["types"] == ["creature", "planeswalker"]
        assert "exclude_types" not in target

    def test_noncreature_spell(self):
        cards = parse_card('''
        card "Test" {
            type: Instant
            cost: {1}{U}
            effect: counter(target(spell | !creature))
        }
        ''')
        target = cards[0].effects[0]["target"]
        assert target["types"] == ["spell"]
        assert target["exclude_types"] == ["creature"]

    def test_all_with_negation(self):
        cards = parse_card('''
        card "Test" {
            type: Sorcery
            cost: {4}{W}{W}
            effect: exile(all(creature | !token))
        }
        ''')
        target = cards[0].effects[0]["target"]
        assert target["kind"] == "all"
        assert target["types"] == ["creature"]
        assert target["exclude_types"] == ["token"]

    def test_negation_with_controller(self):
        cards = parse_card('''
        card "Test" {
            type: Sorcery
            cost: {2}{B}
            effect: destroy(target(permanent | !land, opponent))
        }
        ''')
        target = cards[0].effects[0]["target"]
        assert target["types"] == ["permanent"]
        assert target["exclude_types"] == ["land"]
        assert target["controller"] == "opponent"

    def test_union_with_state(self):
        cards = parse_card('''
        card "Test" {
            type: Sorcery
            cost: {2}{W}
            effect: exile(all(creature | planeswalker, attacking))
        }
        ''')
        target = cards[0].effects[0]["target"]
        assert target["types"] == ["creature", "planeswalker"]
        assert target["state"] == "attacking"

    def test_sacrifice_cost_with_type_expr(self):
        cards = parse_card('''
        card "Test" {
            type: Artifact
            cost: {3}
            activate({0}, sacrifice(permanent | !land)): draw(2)
        }
        ''')
        cost = cards[0].activated_abilities[0]["cost"]
        assert cost["sacrifice"]["types"] == ["permanent"]
        assert cost["sacrifice"]["exclude_types"] == ["land"]

    def test_enchant_type_expr(self):
        cards = parse_card('''
        card "Test" {
            type: Enchantment
            cost: {1}{U}
            enchant: creature | planeswalker
        }
        ''')
        enchant_effect = cards[0].effects[0]
        assert enchant_effect["type"] == "enchant"
        assert enchant_effect["types"] == ["creature", "planeswalker"]

    def test_self_and_each_opponent_unchanged(self):
        cards = parse_card('''
        card "Test" {
            type: Creature
            cost: {B}
            p/t: 1 / 1
            when(dies): lose_life(each_opponent, 2); gain_life(2)
        }
        ''')
        effects = cards[0].triggered_abilities[0]["effects"]
        assert effects[0]["target"]["kind"] == "each_opponent"


class TestMatchesCardType:
    """Tests for the centralized matches_card_type function."""

    def test_creature_matches_creature(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Bear", card_type=CardType.CREATURE)
        assert matches_card_type(card, ["creature"]) is True

    def test_creature_does_not_match_artifact(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Bear", card_type=CardType.CREATURE)
        assert matches_card_type(card, ["artifact"]) is False

    def test_permanent_matches_creature(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Bear", card_type=CardType.CREATURE)
        assert matches_card_type(card, ["permanent"]) is True

    def test_permanent_does_not_match_instant(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Bolt", card_type=CardType.INSTANT)
        assert matches_card_type(card, ["permanent"]) is False

    def test_nonland_permanent_matches_creature(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Bear", card_type=CardType.CREATURE)
        assert matches_card_type(card, ["permanent"], ["land"]) is True

    def test_nonland_permanent_rejects_land(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Forest", card_type=CardType.LAND)
        assert matches_card_type(card, ["permanent"], ["land"]) is False

    def test_union_creature_or_planeswalker(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        pw = Card(name="Jace", card_type=CardType.PLANESWALKER)
        assert matches_card_type(pw, ["creature", "planeswalker"]) is True
        artifact = Card(name="Sol Ring", card_type=CardType.ARTIFACT)
        assert matches_card_type(artifact, ["creature", "planeswalker"]) is False

    def test_noncreature_spell(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        instant = Card(name="Bolt", card_type=CardType.INSTANT)
        assert matches_card_type(instant, ["spell"], ["creature"]) is True
        creature = Card(name="Bear", card_type=CardType.CREATURE)
        assert matches_card_type(creature, ["spell"], ["creature"]) is False

    def test_any_target_matches_everything(self):
        from mtg_engine.core.card import Card
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Bear", card_type=CardType.CREATURE)
        assert matches_card_type(card, ["any_target"]) is True

    def test_token_exclude(self):
        from mtg_engine.core.card import Card, CardInstance
        from mtg_engine.core.filters import matches_card_type
        card = Card(name="Bear", card_type=CardType.CREATURE)
        inst = CardInstance(card=card, is_token=True)
        assert matches_card_type(inst, ["creature"], ["token"]) is False
        inst2 = CardInstance(card=card, is_token=False)
        assert matches_card_type(inst2, ["creature"], ["token"]) is True


class TestNormalizeTarget:
    """Tests for backward-compatible target normalization."""

    def test_old_format_converted(self):
        from mtg_engine.core.filters import normalize_target
        old = {"kind": "target", "target_type": "creature"}
        result = normalize_target(old)
        assert result["types"] == ["creature"]
        assert "target_type" not in result

    def test_new_format_unchanged(self):
        from mtg_engine.core.filters import normalize_target
        new = {"kind": "target", "types": ["permanent"], "exclude_types": ["land"]}
        result = normalize_target(new)
        assert result["types"] == ["permanent"]
        assert result["exclude_types"] == ["land"]

    def test_self_unchanged(self):
        from mtg_engine.core.filters import normalize_target
        target = {"kind": "self"}
        assert normalize_target(target) == {"kind": "self"}

    def test_each_opponent_unchanged(self):
        from mtg_engine.core.filters import normalize_target
        target = {"kind": "each_opponent"}
        assert normalize_target(target) == {"kind": "each_opponent"}
