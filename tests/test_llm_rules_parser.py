"""Tests for the LLM-based rules text translator.

Tests validation logic, normalization, and fallback behavior.
API calls are mocked — no real API key needed.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from mtg_engine.core.keywords import Keyword
from mtg_engine.dsl.llm_rules_parser import (
    _validate_effect,
    _validate_target,
    _validate_result,
    _validate_triggered,
    _validate_activated,
    _normalize_result,
    _build_system_prompt,
    translate_rules_text_llm,
    VALID_EFFECT_TYPES,
    VALID_TARGET_KINDS,
    VALID_TARGET_TYPES,
    VALID_TRIGGER_EVENTS,
    VALID_CONTROLLER_QUALIFIERS,
    VALID_STATE_QUALIFIERS,
    VALID_KEYWORDS,
    EFFECT_TYPE_DOCS,
    SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidateTarget:
    def test_valid_target(self):
        assert _validate_target({"kind": "target", "target_type": "creature"})

    def test_valid_all(self):
        assert _validate_target({"kind": "all", "target_type": "creature"})

    def test_valid_self(self):
        assert _validate_target({"kind": "self"})

    def test_valid_each_opponent(self):
        assert _validate_target({"kind": "each_opponent"})

    def test_invalid_kind(self):
        assert not _validate_target({"kind": "invalid"})

    def test_invalid_target_type(self):
        assert not _validate_target({"kind": "target", "target_type": "dragon"})

    def test_valid_with_controller(self):
        assert _validate_target({"kind": "target", "target_type": "creature", "controller": "opponent"})

    def test_invalid_controller(self):
        assert not _validate_target({"kind": "target", "target_type": "creature", "controller": "enemy"})

    def test_valid_with_state(self):
        assert _validate_target({"kind": "target", "target_type": "creature", "state": "attacking"})

    def test_invalid_state(self):
        assert not _validate_target({"kind": "target", "target_type": "creature", "state": "flying"})


class TestValidateEffect:
    def test_valid_damage(self):
        assert _validate_effect({
            "type": "damage",
            "target": {"kind": "target", "target_type": "creature"},
            "amount": 3,
        })

    def test_invalid_type(self):
        assert not _validate_effect({"type": "fireball"})

    def test_valid_draw(self):
        assert _validate_effect({"type": "draw", "amount": 2})

    def test_valid_may_wrapper(self):
        assert _validate_effect({
            "type": "may",
            "inner_effect": {"type": "draw", "amount": 1},
        })

    def test_invalid_may_inner(self):
        assert not _validate_effect({
            "type": "may",
            "inner_effect": {"type": "fireball"},
        })

    def test_valid_if_did(self):
        assert _validate_effect({
            "type": "if_did",
            "condition_effect": {"type": "sacrifice", "target": {"kind": "target", "target_type": "creature"}},
            "then_effect": {"type": "draw", "amount": 1},
        })

    def test_invalid_if_did_then(self):
        assert not _validate_effect({
            "type": "if_did",
            "condition_effect": {"type": "sacrifice", "target": {"kind": "target", "target_type": "creature"}},
            "then_effect": {"type": "nuke"},
        })

    def test_no_target_ok(self):
        assert _validate_effect({"type": "scry", "amount": 2})

    def test_invalid_target_in_effect(self):
        assert not _validate_effect({
            "type": "damage",
            "target": {"kind": "invalid"},
            "amount": 3,
        })


class TestValidateTriggered:
    def test_valid(self):
        assert _validate_triggered({
            "trigger": "enters_battlefield",
            "source": {"type": "self"},
            "effects": [{"type": "draw", "amount": 1}],
        })

    def test_invalid_trigger(self):
        assert not _validate_triggered({
            "trigger": "explodes",
            "source": {"type": "self"},
            "effects": [{"type": "draw", "amount": 1}],
        })

    def test_invalid_effect_in_trigger(self):
        assert not _validate_triggered({
            "trigger": "dies",
            "source": {"type": "self"},
            "effects": [{"type": "fireball"}],
        })


class TestValidateActivated:
    def test_valid(self):
        assert _validate_activated({
            "cost": {"tap": True},
            "effects": [{"type": "add_mana", "color": "G"}],
        })

    def test_invalid_effect(self):
        assert not _validate_activated({
            "cost": {"tap": True},
            "effects": [{"type": "nope"}],
        })


class TestValidateResult:
    def test_valid_full(self):
        assert _validate_result({
            "effects": [{"type": "damage", "target": {"kind": "target", "target_type": "any_target"}, "amount": 3}],
            "keywords": ["flying"],
            "triggered_abilities": [],
            "activated_abilities": [],
        })

    def test_invalid_keyword(self):
        assert not _validate_result({
            "effects": [],
            "keywords": ["super_flying"],
            "triggered_abilities": [],
            "activated_abilities": [],
        })

    def test_invalid_effect_fails(self):
        assert not _validate_result({
            "effects": [{"type": "nope"}],
            "keywords": [],
            "triggered_abilities": [],
            "activated_abilities": [],
        })


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_keywords_converted_to_enum(self):
        result = _normalize_result({
            "effects": [],
            "keywords": ["flying", "first_strike"],
            "triggered_abilities": [],
            "activated_abilities": [],
        })
        assert result["keywords"] == {Keyword.FLYING, Keyword.FIRST_STRIKE}

    def test_unknown_keywords_dropped(self):
        result = _normalize_result({
            "effects": [],
            "keywords": ["flying", "nonexistent"],
            "triggered_abilities": [],
            "activated_abilities": [],
        })
        assert result["keywords"] == {Keyword.FLYING}


# ---------------------------------------------------------------------------
# Integration tests (mocked API)
# ---------------------------------------------------------------------------

def _mock_api_response(content: dict) -> MagicMock:
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(content)
    mock_response.content = [mock_content]
    return mock_response


class TestTranslateWithMockedAPI:
    """Test translate_rules_text_llm with mocked Claude API calls."""

    @patch("mtg_engine.dsl.llm_rules_parser.anthropic")
    def test_simple_damage(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_api_response({
            "effects": [{"type": "damage", "target": {"kind": "target", "target_type": "any_target"}, "amount": 3}],
            "keywords": [],
            "triggered_abilities": [],
            "activated_abilities": [],
        })

        result = translate_rules_text_llm("Deal 3 damage to any target.", api_key="test-key", fallback=False)
        assert len(result["effects"]) == 1
        assert result["effects"][0]["type"] == "damage"
        assert result["effects"][0]["amount"] == 3

    @patch("mtg_engine.dsl.llm_rules_parser.anthropic")
    def test_keywords(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_api_response({
            "effects": [],
            "keywords": ["flying", "lifelink"],
            "triggered_abilities": [],
            "activated_abilities": [],
        })

        result = translate_rules_text_llm("Flying, lifelink", api_key="test-key", fallback=False)
        assert Keyword.FLYING in result["keywords"]
        assert Keyword.LIFELINK in result["keywords"]

    @patch("mtg_engine.dsl.llm_rules_parser.anthropic")
    def test_triggered_ability(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_api_response({
            "effects": [],
            "keywords": [],
            "triggered_abilities": [{
                "trigger": "enters_battlefield",
                "source": {"type": "self"},
                "effects": [{"type": "draw", "amount": 1}],
            }],
            "activated_abilities": [],
        })

        result = translate_rules_text_llm(
            "When ~ enters the battlefield, draw a card.",
            api_key="test-key",
            fallback=False,
        )
        assert len(result["triggered_abilities"]) == 1
        assert result["triggered_abilities"][0]["trigger"] == "enters_battlefield"

    @patch("mtg_engine.dsl.llm_rules_parser.anthropic")
    def test_validation_failure_falls_back(self, mock_anthropic_module):
        """When LLM returns invalid data and fallback=True, uses regex parser."""
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_api_response({
            "effects": [{"type": "fireball"}],  # Invalid type
            "keywords": [],
            "triggered_abilities": [],
            "activated_abilities": [],
        })

        result = translate_rules_text_llm("Deal 3 damage to any target.", api_key="test-key", fallback=True)
        # Should have fallen back to regex parser, which handles this
        assert len(result["effects"]) == 1
        assert result["effects"][0]["type"] == "damage"

    def test_no_api_key_falls_back(self):
        """Without API key, falls back to regex parser."""
        with patch.dict("os.environ", {}, clear=True):
            result = translate_rules_text_llm("Flying", fallback=True)
            assert Keyword.FLYING in result["keywords"]

    def test_no_api_key_no_fallback(self):
        """Without API key and fallback=False, returns empty."""
        with patch.dict("os.environ", {}, clear=True):
            result = translate_rules_text_llm("Flying", fallback=False)
            assert len(result["keywords"]) == 0

    @patch("mtg_engine.dsl.llm_rules_parser.anthropic")
    def test_loyalty_ability(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_api_response({
            "effects": [],
            "keywords": [],
            "triggered_abilities": [],
            "activated_abilities": [{
                "loyalty_cost": 1,
                "is_loyalty": True,
                "effects": [{"type": "draw", "amount": 1}],
            }],
        })

        result = translate_rules_text_llm("+1: Draw a card", api_key="test-key", fallback=False)
        assert len(result["activated_abilities"]) == 1
        assert result["activated_abilities"][0]["loyalty_cost"] == 1
        assert result["activated_abilities"][0]["is_loyalty"] is True

    @patch("mtg_engine.dsl.llm_rules_parser.anthropic")
    def test_markdown_fences_stripped(self, mock_anthropic_module):
        """LLM sometimes wraps JSON in markdown fences — should handle gracefully."""
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = '```json\n{"effects": [{"type": "draw", "amount": 1}], "keywords": [], "triggered_abilities": [], "activated_abilities": []}\n```'
        mock_response.content = [mock_content]
        mock_client.messages.create.return_value = mock_response

        result = translate_rules_text_llm("Draw a card.", api_key="test-key", fallback=False)
        assert len(result["effects"]) == 1
        assert result["effects"][0]["type"] == "draw"

    @patch("mtg_engine.dsl.llm_rules_parser.anthropic")
    def test_api_exception_falls_back(self, mock_anthropic_module):
        """API errors should trigger fallback."""
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        result = translate_rules_text_llm("Flying", api_key="test-key", fallback=True)
        assert Keyword.FLYING in result["keywords"]


# ---------------------------------------------------------------------------
# Sync tests — ensure VALID_* sets and prompt stay in sync
# ---------------------------------------------------------------------------

class TestPromptSync:
    """Verify that the auto-generated system prompt reflects all VALID_* sets."""

    def test_all_effect_types_documented(self):
        """Every VALID_EFFECT_TYPE must have an entry in EFFECT_TYPE_DOCS."""
        missing = VALID_EFFECT_TYPES - set(EFFECT_TYPE_DOCS.keys())
        assert missing == set(), f"Effect types in VALID_EFFECT_TYPES but not EFFECT_TYPE_DOCS: {missing}"

    def test_no_extra_docs(self):
        """EFFECT_TYPE_DOCS should not contain types not in VALID_EFFECT_TYPES."""
        extra = set(EFFECT_TYPE_DOCS.keys()) - VALID_EFFECT_TYPES
        assert extra == set(), f"Effect types in EFFECT_TYPE_DOCS but not VALID_EFFECT_TYPES: {extra}"

    def test_all_effect_types_in_prompt(self):
        """Every valid effect type must appear in the generated system prompt."""
        for etype in VALID_EFFECT_TYPES:
            assert etype in SYSTEM_PROMPT, f"Effect type {etype!r} missing from system prompt"

    def test_all_target_kinds_in_prompt(self):
        for kind in VALID_TARGET_KINDS:
            assert f'"{kind}"' in SYSTEM_PROMPT, f"Target kind {kind!r} missing from system prompt"

    def test_all_target_types_in_prompt(self):
        for ttype in VALID_TARGET_TYPES:
            assert f'"{ttype}"' in SYSTEM_PROMPT, f"Target type {ttype!r} missing from system prompt"

    def test_all_trigger_events_in_prompt(self):
        for event in VALID_TRIGGER_EVENTS:
            assert f'"{event}"' in SYSTEM_PROMPT, f"Trigger event {event!r} missing from system prompt"

    def test_all_keywords_in_prompt(self):
        for kw in VALID_KEYWORDS:
            assert f'"{kw}"' in SYSTEM_PROMPT, f"Keyword {kw!r} missing from system prompt"

    def test_all_controller_qualifiers_in_prompt(self):
        for ctrl in VALID_CONTROLLER_QUALIFIERS:
            assert f'"{ctrl}"' in SYSTEM_PROMPT, f"Controller qualifier {ctrl!r} missing from system prompt"

    def test_all_state_qualifiers_in_prompt(self):
        for state in VALID_STATE_QUALIFIERS:
            assert f'"{state}"' in SYSTEM_PROMPT, f"State qualifier {state!r} missing from system prompt"

    def test_prompt_builds_without_error(self):
        """Smoke test that _build_system_prompt runs and produces non-empty output."""
        prompt = _build_system_prompt()
        assert len(prompt) > 500
        assert "Effect types and their fields" in prompt
