"""Interactive CLI for playing MTG games turn-by-turn."""

from __future__ import annotations

import sys

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Phase, Step, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost


# ---- Sample cards ----

def _sample_cards() -> dict[str, Card]:
    return {
        "Lightning Bolt": Card(
            name="Lightning Bolt", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 3}],
        ),
        "Grizzly Bears": Card(
            name="Grizzly Bears", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{1}{G}"), power=2, toughness=2,
        ),
        "Giant Growth": Card(
            name="Giant Growth", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{G}"),
            effects=[{"type": "pump", "power": 3, "toughness": 3}],
        ),
        "Serra Angel": Card(
            name="Serra Angel", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{3}{W}{W}"), power=4, toughness=4,
            keywords={Keyword.FLYING, Keyword.VIGILANCE},
        ),
        "Monastery Swiftspear": Card(
            name="Monastery Swiftspear", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{R}"), power=1, toughness=2,
            keywords={Keyword.PROWESS, Keyword.HASTE},
        ),
        "Shock": Card(
            name="Shock", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{R}"),
            effects=[{"type": "damage", "amount": 2}],
        ),
        "Counterspell": Card(
            name="Counterspell", card_type=CardType.INSTANT,
            cost=ManaCost.parse("{U}{U}"),
            effects=[{"type": "counter"}],
        ),
        "Llanowar Elves": Card(
            name="Llanowar Elves", card_type=CardType.CREATURE,
            cost=ManaCost.parse("{G}"), power=1, toughness=1,
        ),
        "Blaze": Card(
            name="Blaze", card_type=CardType.SORCERY,
            cost=ManaCost.parse("{X}{R}"),
            effects=[{"type": "x_damage"}],
        ),
        "Mountain": Card(name="Mountain", card_type=CardType.LAND),
        "Forest": Card(name="Forest", card_type=CardType.LAND),
        "Island": Card(name="Island", card_type=CardType.LAND),
        "Plains": Card(name="Plains", card_type=CardType.LAND),
        "Swamp": Card(name="Swamp", card_type=CardType.LAND),
    }


# ---- Display ----

def _mana_str(pool) -> str:
    parts = []
    if pool.white: parts.append(f"W:{pool.white}")
    if pool.blue: parts.append(f"U:{pool.blue}")
    if pool.black: parts.append(f"B:{pool.black}")
    if pool.red: parts.append(f"R:{pool.red}")
    if pool.green: parts.append(f"G:{pool.green}")
    if pool.colorless: parts.append(f"C:{pool.colorless}")
    return " ".join(parts) if parts else "(empty)"


def _card_short(card: CardInstance) -> str:
    parts = [f"[{card.instance_id[:4]}]", card.name]
    if card.card.is_creature:
        parts.append(f"{card.current_power}/{card.current_toughness}")
        if card.damage_marked:
            parts.append(f"({card.damage_marked}dmg)")
    if card.tapped:
        parts.append("(T)")
    kws = [kw.name.lower() for kw in card.keywords]
    if kws:
        parts.append(f"[{','.join(kws)}]")
    return " ".join(parts)


def show_state(game: Game, viewer: int = 0) -> None:
    s = game.state
    print()
    print("=" * 60)
    print(f"  Turn {s.turn_number} | {s.phase.name} / {s.step.name} "
          f"| Active: {s.active_player.name} "
          f"| Priority: {s.priority_player.name}")
    print("=" * 60)

    for i, player in enumerate(s.players):
        tag = " <<" if i == s.active_player_index else ""
        print(f"\n  {player.name}: {player.life} life | "
              f"Mana: {_mana_str(player.mana_pool)} | "
              f"Poison: {player.poison_counters}{tag}")

        bf = s.get_battlefield(i)
        lands = [c for c in bf if c.card.is_land]
        nonlands = [c for c in bf if not c.card.is_land]
        if lands:
            print(f"    Lands:      {', '.join(_card_short(c) for c in lands)}")
        if nonlands:
            print(f"    Permanents: {', '.join(_card_short(c) for c in nonlands)}")

        hand = s.get_zone(i, Zone.HAND)
        if i == viewer:
            print(f"    Hand ({len(hand)}):  {', '.join(_card_short(c) for c in hand)}")
        else:
            print(f"    Hand: {len(hand)} cards")

        gy = s.get_zone(i, Zone.GRAVEYARD)
        if gy:
            print(f"    Graveyard:  {', '.join(c.name for c in gy)}")

    if not s.stack.is_empty:
        print(f"\n  Stack ({s.stack.size}):")
        for item in reversed(s.stack._items):
            print(f"    -> {item.card_name}")
    print()


def show_help() -> None:
    print("""
Commands:
  state / s          Show game state
  hand               Show your hand in detail
  play <id>          Play a land (by 4-char ID prefix)
  tap <id>           Tap a land for mana
  cast <id> [t1 t2]  Cast a spell (targets by name or ID)
  cast <id> x=N      Cast X spell with chosen X value
  resolve / r        Resolve top of stack
  attack <id> [id..] Declare attackers
  block <b_id> <a_id> Declare blocker -> attacker
  damage             Resolve combat damage
  pass / p           Pass priority / advance step
  next               Advance to next step
  turn               Advance to next turn
  cycle <id>         Activate cycling
  log                Show game log (last 20)
  help / h           Show this help
  quit / q           Exit
""")


# ---- Lookup ----

def find_card(game: Game, prefix: str) -> CardInstance | None:
    prefix = prefix.lower()
    for c in game.state.cards:
        if c.instance_id.lower().startswith(prefix):
            return c
    return None


def find_target(game: Game, name: str) -> str | None:
    for p in game.state.players:
        if p.name.lower() == name.lower():
            return p.name
    card = find_card(game, name)
    if card:
        return card.instance_id
    return None


# ---- Main loop ----

def interactive_game(game: Game, viewer: int = 0) -> None:
    print("\n=== MTG Rules Engine - Interactive Game ===")
    print("Type 'help' for commands.\n")

    game.draw_opening_hands()
    game.run_step()  # untap
    show_state(game, viewer)

    while True:
        try:
            raw = input(f"{game.state.players[viewer].name}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd in ("quit", "q"):
                print("Goodbye!")
                break

            elif cmd in ("help", "h"):
                show_help()

            elif cmd in ("state", "s"):
                show_state(game, viewer)

            elif cmd == "hand":
                hand = game.state.get_zone(viewer, Zone.HAND)
                print(f"\nYour hand ({len(hand)} cards):")
                for c in hand:
                    tp = c.card.card_type.name
                    extra = f" {c.card.power}/{c.card.toughness}" if c.card.is_creature else ""
                    kws = [kw.name.lower() for kw in c.card.keywords]
                    kw_str = f" [{', '.join(kws)}]" if kws else ""
                    print(f"  [{c.instance_id[:4]}] {c.name} {c.card.cost} - {tp}{extra}{kw_str}")
                print()

            elif cmd == "play":
                if not args:
                    print("Usage: play <card-id>"); continue
                card = find_card(game, args[0])
                if not card:
                    print(f"Card not found: {args[0]}"); continue
                if game.play_land(viewer, card.instance_id):
                    print(f"Played {card.name}")
                    show_state(game, viewer)
                else:
                    print(f"Can't play {card.name}")

            elif cmd == "tap":
                if not args:
                    print("Usage: tap <card-id>"); continue
                card = find_card(game, args[0])
                if not card:
                    print(f"Card not found: {args[0]}"); continue
                if game.tap_land_for_mana(viewer, card.instance_id):
                    print(f"Tapped {card.name}. Pool: {_mana_str(game.state.players[viewer].mana_pool)}")
                else:
                    print(f"Can't tap {card.name}")

            elif cmd == "cast":
                if not args:
                    print("Usage: cast <card-id> [target1 ...] [x=N] [kicked]"); continue
                card = find_card(game, args[0])
                if not card:
                    print(f"Card not found: {args[0]}"); continue
                x_val, targets, kicked = 0, [], False
                for a in args[1:]:
                    if a.startswith("x="):
                        x_val = int(a[2:])
                    elif a == "kicked":
                        kicked = True
                    else:
                        t = find_target(game, a)
                        if t:
                            targets.append(t)
                        else:
                            print(f"Target not found: {a}")
                ok = game.cast_spell(viewer, card.instance_id,
                                     targets=targets or None, x_value=x_val, kicked=kicked)
                if ok:
                    x_str = f" (X={x_val})" if x_val else ""
                    print(f"Cast {card.name}{x_str}")
                    show_state(game, viewer)
                else:
                    print(f"Can't cast {card.name} (check mana/timing)")

            elif cmd in ("resolve", "r"):
                if game.state.stack.is_empty:
                    print("Stack is empty")
                else:
                    result = game.resolve_top_of_stack()
                    if result:
                        msg = f"Resolved: {result['card_name']}"
                        if result.get("fizzled"):
                            msg += " (fizzled)"
                        print(msg)
                    show_state(game, viewer)

            elif cmd == "attack":
                if not args:
                    print("Usage: attack <id1> [id2 ...]"); continue
                ids = []
                for a in args:
                    c = find_card(game, a)
                    if c: ids.append(c.instance_id)
                    else: print(f"Card not found: {a}")
                valid = game.declare_attackers(ids)
                print(f"Attacking with {len(valid)} creature(s)")
                show_state(game, viewer)

            elif cmd == "block":
                if len(args) < 2:
                    print("Usage: block <blocker-id> <attacker-id>"); continue
                blocker = find_card(game, args[0])
                attacker = find_card(game, args[1])
                if not blocker or not attacker:
                    print("Card not found"); continue
                valid = game.declare_blockers({blocker.instance_id: attacker.instance_id})
                if valid:
                    print(f"{blocker.name} blocks {attacker.name}")
                else:
                    print("Invalid block")
                show_state(game, viewer)

            elif cmd == "damage":
                log = game.resolve_combat_damage()
                for entry in log:
                    print(f"  {entry}")
                show_state(game, viewer)

            elif cmd in ("pass", "p"):
                game.state.pass_priority()
                if len(game.state.players_passed) >= len(game.state.players):
                    if not game.state.stack.is_empty:
                        result = game.resolve_top_of_stack()
                        if result:
                            print(f"Resolved: {result['card_name']}")
                    else:
                        game.advance_step()
                        game.run_step()
                        print(f"Advanced to {game.state.phase.name}/{game.state.step.name}")
                else:
                    print("Priority passed")
                show_state(game, viewer)

            elif cmd == "next":
                game.advance_step()
                game.run_step()
                print(f"Now: {game.state.phase.name}/{game.state.step.name}")
                show_state(game, viewer)

            elif cmd == "turn":
                game.advance_turn()
                game.state.phase, game.state.step = Phase.BEGINNING, Step.UNTAP
                game.run_step()
                game.advance_step()
                game.run_step()  # draw
                game.advance_step()  # main
                print(f"Turn {game.state.turn_number}: {game.state.active_player.name}")
                show_state(game, viewer)

            elif cmd == "cycle":
                if not args:
                    print("Usage: cycle <card-id>"); continue
                card = find_card(game, args[0])
                if not card:
                    print(f"Card not found: {args[0]}"); continue
                if game.activate_cycling(viewer, card.instance_id):
                    print(f"Cycled {card.name}")
                    show_state(game, viewer)
                else:
                    print(f"Can't cycle {card.name}")

            elif cmd == "log":
                print("\n--- Game Log ---")
                for entry in game.log[-20:]:
                    print(f"  {entry}")
                print()

            else:
                print(f"Unknown command: {cmd}. Type 'help' for commands.")

        except Exception as e:
            print(f"Error: {e}")

        # Check game over
        for p in game.state.players:
            if p.lost:
                print(f"\n{'='*40}")
                print(f"  {p.name} has lost the game!")
                print(f"{'='*40}\n")


def build_default_game() -> Game:
    cards = _sample_cards()
    deck1 = (
        [cards["Lightning Bolt"]] * 4 + [cards["Monastery Swiftspear"]] * 4
        + [cards["Shock"]] * 4 + [cards["Blaze"]] * 2 + [cards["Mountain"]] * 26
    )
    deck2 = (
        [cards["Grizzly Bears"]] * 4 + [cards["Llanowar Elves"]] * 4
        + [cards["Giant Growth"]] * 4 + [cards["Serra Angel"]] * 2
        + [cards["Forest"]] * 18 + [cards["Plains"]] * 8
    )
    return Game(["You", "Opponent"], [deck1, deck2])


def run_interactive() -> None:
    game = build_default_game()
    interactive_game(game, viewer=0)
