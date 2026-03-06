"""Tests for sideboard and outside-the-game mechanics."""

import pytest

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Zone
from mtg_engine.core.mana import ManaCost
from mtg_engine.core.sideboard import (
    SIDEBOARD_SIZE_CONSTRUCTED,
    Sideboard,
    create_sideboard,
    learn,
    swap_sideboard_card,
    validate_sideboard,
    wish,
    wish_for_card,
)


def _make_cards():
    return [
        Card(name="Lightning Bolt", card_type=CardType.INSTANT,
             cost=ManaCost.parse("{R}")),
        Card(name="Counterspell", card_type=CardType.INSTANT,
             cost=ManaCost.parse("{U}{U}")),
        Card(name="Grizzly Bears", card_type=CardType.CREATURE,
             cost=ManaCost.parse("{1}{G}"), power=2, toughness=2),
        Card(name="Academic Dispute", card_type=CardType.INSTANT,
             cost=ManaCost.parse("{R}"), subtypes=["Lesson"]),
        Card(name="Environmental Sciences", card_type=CardType.SORCERY,
             cost=ManaCost.parse("{2}"), subtypes=["Lesson"]),
    ]


class TestCreateSideboard:
    def test_create(self):
        cards = _make_cards()
        sb = create_sideboard(cards, owner_index=0)
        assert sb.size == 5
        assert sb.owner_index == 0

    def test_empty_sideboard(self):
        sb = create_sideboard([], owner_index=1)
        assert sb.size == 0


class TestSideboardSearch:
    def test_find_by_name(self):
        sb = create_sideboard(_make_cards())
        results = sb.find_by_name("Lightning Bolt")
        assert len(results) == 1
        assert results[0].card.name == "Lightning Bolt"

    def test_find_by_type(self):
        sb = create_sideboard(_make_cards())
        instants = sb.find_by_type(CardType.INSTANT)
        assert len(instants) == 3  # Bolt, Counterspell, Academic Dispute

    def test_find_by_subtype(self):
        sb = create_sideboard(_make_cards())
        lessons = sb.find_by_subtype("Lesson")
        assert len(lessons) == 2

    def test_find_nonexistent(self):
        sb = create_sideboard(_make_cards())
        results = sb.find_by_name("Nonexistent Card")
        assert len(results) == 0


class TestWish:
    def test_wish_for_type(self):
        sb = create_sideboard(_make_cards())
        creatures = wish(sb, card_type=CardType.CREATURE)
        assert len(creatures) == 1
        assert creatures[0].card.name == "Grizzly Bears"

    def test_wish_all(self):
        sb = create_sideboard(_make_cards())
        all_cards = wish(sb)
        assert len(all_cards) == 5

    def test_wish_for_specific_card(self):
        sb = create_sideboard(_make_cards())
        bolt = sb.find_by_name("Lightning Bolt")[0]
        result = wish_for_card(sb, bolt.instance_id)
        assert result is not None
        assert result.card.name == "Lightning Bolt"
        assert sb.size == 4  # Removed from sideboard

    def test_wish_for_nonexistent(self):
        sb = create_sideboard(_make_cards())
        result = wish_for_card(sb, "nonexistent_id")
        assert result is None
        assert sb.size == 5


class TestLearn:
    def test_learn_finds_lessons(self):
        sb = create_sideboard(_make_cards())
        lessons = learn(sb)
        assert len(lessons) == 2
        assert all("Lesson" in c.card.subtypes for c in lessons)

    def test_learn_no_lessons(self):
        cards = [
            Card(name="Bolt", card_type=CardType.INSTANT,
                 cost=ManaCost.parse("{R}")),
        ]
        sb = create_sideboard(cards)
        lessons = learn(sb)
        assert len(lessons) == 0


class TestSwapSideboard:
    def test_swap_card(self):
        sb = create_sideboard(_make_cards())
        bolt = sb.find_by_name("Lightning Bolt")[0]

        game_card = CardInstance(
            card=Card(name="Shock", card_type=CardType.INSTANT,
                      cost=ManaCost.parse("{R}")),
            zone=Zone.LIBRARY,
        )

        incoming = swap_sideboard_card(sb, bolt.instance_id, game_card)
        assert incoming is not None
        assert incoming.card.name == "Lightning Bolt"
        # Shock should now be in sideboard
        assert sb.find_by_name("Shock")
        # Bolt should be removed from sideboard
        assert not sb.find_by_name("Lightning Bolt")

    def test_swap_nonexistent(self):
        sb = create_sideboard(_make_cards())
        game_card = CardInstance(
            card=Card(name="Shock", card_type=CardType.INSTANT,
                      cost=ManaCost.parse("{R}")),
            zone=Zone.LIBRARY,
        )
        result = swap_sideboard_card(sb, "nonexistent", game_card)
        assert result is None


class TestValidation:
    def test_valid_sideboard(self):
        cards = _make_cards()
        sb = create_sideboard(cards)
        errors = validate_sideboard(sb)
        assert len(errors) == 0

    def test_oversized_sideboard(self):
        cards = [
            Card(name=f"Card {i}", card_type=CardType.INSTANT,
                 cost=ManaCost.parse("{1}"))
            for i in range(20)
        ]
        sb = create_sideboard(cards)
        errors = validate_sideboard(sb)
        assert len(errors) > 0
        assert any("maximum" in e.lower() for e in errors)

    def test_max_size_constant(self):
        assert SIDEBOARD_SIZE_CONSTRUCTED == 15
