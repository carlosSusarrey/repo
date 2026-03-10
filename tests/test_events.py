"""Tests for the centralized event system (EventBus, GameEvent, typed data)."""

import pytest
from unittest.mock import MagicMock, patch

from mtg_engine.core.events import (
    EventBus,
    EventData,
    GameEvent,
    ZoneChangeEventData,
    DamageEventData,
    LifeEventData,
    SpellEventData,
    DrawEventData,
    PhaseEventData,
    _REPLACEABLE_EVENTS,
    _game_event_to_trigger,
    _game_event_to_replacement,
)
from mtg_engine.core.replacement_effects import ReplacementType
from mtg_engine.core.triggers import TriggerEvent


# ---------------------------------------------------------------------------
# GameEvent enum coverage
# ---------------------------------------------------------------------------


class TestGameEvent:
    def test_has_all_trigger_events(self):
        """Every TriggerEvent should have a matching GameEvent."""
        for te in TriggerEvent:
            assert hasattr(GameEvent, te.name), (
                f"GameEvent missing {te.name} from TriggerEvent"
            )

    def test_has_all_replacement_types(self):
        """Every ReplacementType concept should have a GameEvent counterpart."""
        # The mapping covers all replacement types
        for rt in ReplacementType:
            found = any(
                _game_event_to_replacement(ge) == rt for ge in GameEvent
            )
            assert found, f"No GameEvent maps to ReplacementType.{rt.name}"


# ---------------------------------------------------------------------------
# Typed event data
# ---------------------------------------------------------------------------


class TestEventData:
    def test_zone_change_to_dict(self):
        data = ZoneChangeEventData(
            card_id="abc", card=None, player_index=0, cause="destroy"
        )
        d = data.to_dict()
        assert d["card_id"] == "abc"
        assert d["player_index"] == 0
        assert d["cause"] == "destroy"
        # None fields are excluded
        assert "from_zone" not in d
        assert "to_zone" not in d
        assert "card" not in d

    def test_damage_to_dict(self):
        data = DamageEventData(source_id="src", target="tgt", amount=3)
        d = data.to_dict()
        assert d["amount"] == 3
        assert d["source_id"] == "src"
        assert d["target"] == "tgt"
        assert d["is_combat"] is False  # default, truthy

    def test_life_to_dict(self):
        data = LifeEventData(player_index=1, amount=5)
        d = data.to_dict()
        assert d == {"player_index": 1, "amount": 5}

    def test_from_dict_round_trip(self):
        data = SpellEventData(card_id="xyz", card=None, player_index=1)
        d = data.to_dict()
        reconstructed = SpellEventData.from_dict(d)
        assert reconstructed.card_id == "xyz"
        assert reconstructed.player_index == 1

    def test_from_dict_ignores_unknown_keys(self):
        d = {"player_index": 0, "extra_stuff": 42}
        data = DrawEventData.from_dict(d)
        assert data.player_index == 0


# ---------------------------------------------------------------------------
# Mapping functions
# ---------------------------------------------------------------------------


class TestMappings:
    def test_trigger_mapping(self):
        assert _game_event_to_trigger(GameEvent.DIES) == TriggerEvent.DIES
        assert _game_event_to_trigger(GameEvent.CAST) == TriggerEvent.CAST
        assert _game_event_to_trigger(GameEvent.ENTERS_BATTLEFIELD) == TriggerEvent.ENTERS_BATTLEFIELD

    def test_replacement_mapping(self):
        assert _game_event_to_replacement(GameEvent.DIES) == ReplacementType.DIE
        assert _game_event_to_replacement(GameEvent.DAMAGE) == ReplacementType.DAMAGE
        assert _game_event_to_replacement(GameEvent.DRAW_CARD) == ReplacementType.DRAW
        assert _game_event_to_replacement(GameEvent.GAIN_LIFE) == ReplacementType.LIFE_GAIN
        assert _game_event_to_replacement(GameEvent.ENTERS_BATTLEFIELD) == ReplacementType.ENTER_BATTLEFIELD

    def test_non_replaceable_returns_none(self):
        assert _game_event_to_replacement(GameEvent.CAST) is None
        assert _game_event_to_replacement(GameEvent.ATTACKS) is None

    def test_replaceable_events_set(self):
        assert GameEvent.DIES in _REPLACEABLE_EVENTS
        assert GameEvent.DAMAGE in _REPLACEABLE_EVENTS
        assert GameEvent.CAST not in _REPLACEABLE_EVENTS
        assert GameEvent.ATTACKS not in _REPLACEABLE_EVENTS


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class TestEventBus:
    def _make_bus(self):
        trigger_mgr = MagicMock()
        replacement_mgr = MagicMock()
        bus = EventBus(trigger_mgr, replacement_mgr)
        return bus, trigger_mgr, replacement_mgr

    def test_emit_triggers_only_fires_triggers(self):
        bus, trigger_mgr, repl_mgr = self._make_bus()
        data = {"card_id": "c1", "player_index": 0}
        bus.emit_triggers_only(GameEvent.CAST, data, [])
        trigger_mgr.check_triggers.assert_called_once()
        repl_mgr.check_replacement.assert_not_called()

    def test_emit_replacement_only_checks_replacement(self):
        bus, trigger_mgr, repl_mgr = self._make_bus()
        repl_mgr.check_replacement.return_value = {"amount": 5}
        result = bus.emit_replacement_only(
            GameEvent.DAMAGE, {"amount": 3, "target": "p1"})
        assert result == {"amount": 5}
        repl_mgr.check_replacement.assert_called_once()
        trigger_mgr.check_triggers.assert_not_called()

    def test_emit_replacement_only_returns_none_on_prevent(self):
        bus, _, repl_mgr = self._make_bus()
        repl_mgr.check_replacement.return_value = None
        result = bus.emit_replacement_only(
            GameEvent.DIES, {"card_id": "c1"})
        assert result is None

    def test_emit_non_replaceable_skips_replacement(self):
        bus, trigger_mgr, repl_mgr = self._make_bus()
        repl_mgr.check_replacement.return_value = {"card_id": "c1"}
        result = bus.emit(GameEvent.CAST, {"card_id": "c1"}, [])
        # CAST is not replaceable, so replacement should NOT be called
        repl_mgr.check_replacement.assert_not_called()
        # But triggers should fire
        trigger_mgr.check_triggers.assert_called_once()
        assert result is not None

    def test_emit_replaceable_checks_both(self):
        bus, trigger_mgr, repl_mgr = self._make_bus()
        repl_mgr.check_replacement.return_value = {"card_id": "c1", "modified": True}
        result = bus.emit(
            GameEvent.DIES, {"card_id": "c1"}, ["bf_card"])
        # Both called
        repl_mgr.check_replacement.assert_called_once()
        trigger_mgr.check_triggers.assert_called_once()
        assert result["modified"] is True

    def test_emit_prevented_event_skips_triggers(self):
        bus, trigger_mgr, repl_mgr = self._make_bus()
        repl_mgr.check_replacement.return_value = None  # prevented
        result = bus.emit(
            GameEvent.DIES, {"card_id": "c1"}, [])
        assert result is None
        # Triggers should NOT fire for prevented events
        trigger_mgr.check_triggers.assert_not_called()

    def test_emit_with_typed_data(self):
        bus, trigger_mgr, repl_mgr = self._make_bus()
        data = DamageEventData(source_id="s1", target="p1", amount=3)
        repl_mgr.check_replacement.return_value = data.to_dict()
        result = bus.emit(GameEvent.DAMAGE, data, [])
        assert result["amount"] == 3

    def test_emit_replacement_only_non_replaceable(self):
        """Non-replaceable event returns the data unchanged."""
        bus, _, _ = self._make_bus()
        data = {"card_id": "c1"}
        result = bus.emit_replacement_only(GameEvent.CAST, data)
        assert result == data


# ---------------------------------------------------------------------------
# DSL grammar: unified GAME_EVENT terminal
# ---------------------------------------------------------------------------


class TestDSLUnifiedEvent:
    def test_trigger_with_new_event_name(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Test" {
                type: Creature
                cost: {1}{R}
                p/t: 2 / 2
                when(dies): draw(1)
            }
        ''')
        assert len(cards[0].triggered_abilities) == 1
        assert cards[0].triggered_abilities[0]["trigger"] == "dies"

    def test_replacement_old_name_still_parses(self):
        """Old-style `replace(die):` still works via alias."""
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Phoenix" {
                type: Creature
                cost: {3}{R}
                p/t: 3 / 3
                replace(die): prevent
            }
        ''')
        repl = cards[0].replacement_effects[0]
        # Parser normalizes "die" → "dies"
        assert repl["type"] == "dies"

    def test_replacement_new_name_parses(self):
        """New-style `replace(dies):` also works."""
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Phoenix2" {
                type: Creature
                cost: {3}{R}
                p/t: 3 / 3
                replace(dies): prevent
            }
        ''')
        repl = cards[0].replacement_effects[0]
        assert repl["type"] == "dies"

    def test_replacement_enters_battlefield_new_name(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Tapland" {
                type: Land
                replace(enters_battlefield): enter_tapped
            }
        ''')
        repl = cards[0].replacement_effects[0]
        assert repl["type"] == "enters_battlefield"

    def test_replacement_gain_life_new_name(self):
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Doubler" {
                type: Enchantment
                cost: {4}{W}
                replace(gain_life, any): double_life
            }
        ''')
        repl = cards[0].replacement_effects[0]
        assert repl["type"] == "gain_life"

    def test_replacement_draw_card_new_name(self):
        """New unified name `draw_card` works for replacement."""
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Notion Thief" {
                type: Creature
                cost: {2}{U}{B}
                p/t: 3 / 1
                replace(draw_card, any): prevent
            }
        ''')
        repl = cards[0].replacement_effects[0]
        assert repl["type"] == "draw_card"

    def test_trigger_and_replacement_same_event_name(self):
        """A card can use the same event name for both trigger and replacement."""
        from mtg_engine.dsl.parser import parse_card
        cards = parse_card('''
            card "Complex" {
                type: Creature
                cost: {3}{B}
                p/t: 2 / 2
                when(dies): draw(1)
                replace(dies): prevent
            }
        ''')
        card = cards[0]
        assert len(card.triggered_abilities) == 1
        assert card.triggered_abilities[0]["trigger"] == "dies"
        assert len(card.replacement_effects) == 1
        assert card.replacement_effects[0]["type"] == "dies"
