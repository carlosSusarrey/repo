"""Card DSL - Define MTG cards using a human-readable grammar."""

from mtg_engine.dsl.parser import parse_card, parse_card_file

__all__ = ["parse_card", "parse_card_file"]
