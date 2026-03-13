"""Card DSL - Define MTG cards using a human-readable grammar."""

from mtg_engine.dsl.parser import parse_card, parse_card_file
from mtg_engine.dsl.rules_parser import translate_rules_text

__all__ = ["parse_card", "parse_card_file", "translate_rules_text"]
