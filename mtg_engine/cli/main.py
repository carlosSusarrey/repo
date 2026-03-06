"""CLI entry point for the MTG rules engine."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mtg_engine.core import Card, CardType, Game, ManaCost
from mtg_engine.dsl import parse_card, parse_card_file


def cmd_parse(args: argparse.Namespace) -> None:
    """Parse and display card definitions from a .mtg file."""
    filepath = args.file
    if not Path(filepath).exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    cards = parse_card_file(filepath)
    print(f"Parsed {len(cards)} card(s) from {filepath}:\n")
    for card in cards:
        print(f"  {card.name}")
        print(f"    Type: {card.card_type.name}")
        print(f"    Cost: {card.cost}")
        if card.subtypes:
            print(f"    Subtypes: {', '.join(card.subtypes)}")
        if card.is_creature:
            print(f"    P/T: {card.power}/{card.toughness}")
        if card.rules_text:
            print(f"    Rules: {card.rules_text}")
        if card.effects:
            print(f"    Effects: {len(card.effects)} defined")
        print()


def cmd_simulate(args: argparse.Namespace) -> None:
    """Run a quick simulation with sample cards."""
    # Create some sample cards for a quick demo
    bolt = Card(
        name="Lightning Bolt",
        card_type=CardType.INSTANT,
        cost=ManaCost.parse("{R}"),
        effects=[{"type": "damage", "amount": 3}],
    )
    bear = Card(
        name="Grizzly Bears",
        card_type=CardType.CREATURE,
        cost=ManaCost.parse("{1}{G}"),
        power=2,
        toughness=2,
    )
    mountain = Card(name="Mountain", card_type=CardType.LAND)
    forest = Card(name="Forest", card_type=CardType.LAND)

    # Build simple decks
    deck1 = [bolt] * 20 + [mountain] * 20
    deck2 = [bear] * 20 + [forest] * 20

    game = Game(["Alice", "Bob"], [deck1, deck2])
    game.draw_opening_hands()

    print("=== Game Simulation ===\n")
    print("Players:")
    for i, player in enumerate(game.state.players):
        hand = game.state.get_zone(i, zone=__import__("mtg_engine.core.enums", fromlist=["Zone"]).Zone.HAND)
        print(f"  {player.name}: {player.life} life, {len(hand)} cards in hand")

    print("\nHands:")
    for i, player in enumerate(game.state.players):
        hand = game.state.get_zone(i, zone=__import__("mtg_engine.core.enums", fromlist=["Zone"]).Zone.HAND)
        cards_str = ", ".join(c.name for c in hand)
        print(f"  {player.name}: {cards_str}")

    print("\nGame log:")
    for entry in game.log:
        print(f"  {entry}")

    print("\nSimulation ready. Full interactive mode coming soon!")


def cmd_inspect(args: argparse.Namespace) -> None:
    """Inspect a single card definition from inline DSL."""
    text = args.text
    try:
        cards = parse_card(text)
        for card in cards:
            print(f"Name: {card.name}")
            print(f"Type: {card.card_type.name}")
            print(f"Cost: {card.cost} (CMC: {card.cost.converted_mana_cost})")
            print(f"Colors: {', '.join(c.name for c in card.colors) or 'Colorless'}")
            if card.is_creature:
                print(f"P/T: {card.power}/{card.toughness}")
            if card.effects:
                for i, effect in enumerate(card.effects):
                    print(f"Effect {i+1}: {effect}")
    except Exception as e:
        print(f"Parse error: {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mtg",
        description="MTG Rules Engine - Design and test custom Magic: The Gathering cards",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # parse command
    parse_parser = subparsers.add_parser("parse", help="Parse a .mtg card file")
    parse_parser.add_argument("file", help="Path to .mtg card definition file")

    # simulate command
    sim_parser = subparsers.add_parser("simulate", help="Run a game simulation")

    # inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect inline card DSL")
    inspect_parser.add_argument("text", help="Card DSL text to parse")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "parse": cmd_parse,
        "simulate": cmd_simulate,
        "inspect": cmd_inspect,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
