"""Flask web application for card design and game simulation."""

from __future__ import annotations

import secrets

from flask import Flask, render_template, request, jsonify, session

from mtg_engine.core.card import Card, CardInstance
from mtg_engine.core.enums import CardType, Color, Phase, Step, Zone
from mtg_engine.core.game import Game
from mtg_engine.core.keywords import Keyword
from mtg_engine.core.mana import ManaCost
from mtg_engine.dsl import parse_card


app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# In-memory game storage keyed by session id
_games: dict[str, Game] = {}


# ---- Sample decks ----

def _build_game() -> Game:
    bolt = Card(name="Lightning Bolt", card_type=CardType.INSTANT,
                cost=ManaCost.parse("{R}"), effects=[{"type": "damage", "amount": 3}])
    swiftspear = Card(name="Monastery Swiftspear", card_type=CardType.CREATURE,
                      cost=ManaCost.parse("{R}"), power=1, toughness=2,
                      keywords={Keyword.PROWESS, Keyword.HASTE})
    shock = Card(name="Shock", card_type=CardType.INSTANT,
                 cost=ManaCost.parse("{R}"), effects=[{"type": "damage", "amount": 2}])
    blaze = Card(name="Blaze", card_type=CardType.SORCERY,
                 cost=ManaCost.parse("{X}{R}"), effects=[{"type": "x_damage"}])
    mountain = Card(name="Mountain", card_type=CardType.LAND)

    bear = Card(name="Grizzly Bears", card_type=CardType.CREATURE,
                cost=ManaCost.parse("{1}{G}"), power=2, toughness=2)
    angel = Card(name="Serra Angel", card_type=CardType.CREATURE,
                 cost=ManaCost.parse("{3}{W}{W}"), power=4, toughness=4,
                 keywords={Keyword.FLYING, Keyword.VIGILANCE})
    growth = Card(name="Giant Growth", card_type=CardType.INSTANT,
                  cost=ManaCost.parse("{G}"),
                  effects=[{"type": "pump", "power": 3, "toughness": 3}])
    forest = Card(name="Forest", card_type=CardType.LAND)
    plains = Card(name="Plains", card_type=CardType.LAND)

    deck1 = [bolt]*4 + [swiftspear]*4 + [shock]*4 + [blaze]*2 + [mountain]*26
    deck2 = [bear]*4 + [angel]*2 + [growth]*4 + [forest]*18 + [plains]*12

    game = Game(["You", "Opponent"], [deck1, deck2])
    game.draw_opening_hands()
    game.run_step()
    return game


# ---- Serialization ----

def _ser_card(card: CardInstance) -> dict:
    d = {
        "id": card.instance_id,
        "id_short": card.instance_id[:4],
        "name": card.name,
        "type": card.card.card_type.name,
        "cost": str(card.card.cost),
        "tapped": card.tapped,
        "is_land": card.card.is_land,
        "is_creature": card.card.is_creature,
    }
    if card.card.is_creature:
        d["power"] = card.current_power
        d["toughness"] = card.current_toughness
        d["damage"] = card.damage_marked
    kws = [kw.name.lower() for kw in card.keywords]
    if kws:
        d["keywords"] = kws
    return d


def _ser_state(game: Game, viewer: int = 0) -> dict:
    s = game.state
    players = []
    for i, p in enumerate(s.players):
        hand = s.get_zone(i, Zone.HAND)
        bf = s.get_battlefield(i)
        gy = s.get_zone(i, Zone.GRAVEYARD)
        pd = {
            "name": p.name, "life": p.life, "poison": p.poison_counters,
            "is_active": i == s.active_player_index,
            "mana": {"W": p.mana_pool.white, "U": p.mana_pool.blue,
                     "B": p.mana_pool.black, "R": p.mana_pool.red,
                     "G": p.mana_pool.green, "C": p.mana_pool.colorless},
            "hand_count": len(hand),
            "lands": [_ser_card(c) for c in bf if c.card.is_land],
            "permanents": [_ser_card(c) for c in bf if not c.card.is_land],
            "graveyard": [{"name": c.name} for c in gy],
        }
        if i == viewer:
            pd["hand"] = [_ser_card(c) for c in hand]
        players.append(pd)

    stack_items = [{"name": item.card_name} for item in reversed(s.stack._items)]
    return {
        "turn": s.turn_number, "phase": s.phase.name, "step": s.step.name,
        "active_player": s.active_player.name,
        "priority_player": s.priority_player.name,
        "players": players, "stack": stack_items,
        "log": game.log[-30:], "game_over": s.game_over,
    }


def _get_game() -> Game:
    sid = session.get("game_id")
    if sid and sid in _games:
        return _games[sid]
    sid = secrets.token_hex(8)
    session["game_id"] = sid
    game = _build_game()
    _games[sid] = game
    return game


# ---- Routes ----

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/game")
def game_page():
    return render_template("game.html")


@app.route("/api/parse", methods=["POST"])
def api_parse():
    data = request.get_json()
    dsl_text = data.get("dsl", "")
    try:
        cards = parse_card(dsl_text)
        result = []
        for card in cards:
            cd = {"name": card.name, "type": card.card_type.name,
                  "cost": str(card.cost), "cmc": card.cost.converted_mana_cost,
                  "colors": [c.name for c in card.colors],
                  "rules_text": card.rules_text, "effects": card.effects}
            if card.subtypes: cd["subtypes"] = card.subtypes
            if card.is_creature: cd["power"] = card.power; cd["toughness"] = card.toughness
            if card.loyalty is not None: cd["loyalty"] = card.loyalty
            result.append(cd)
        return jsonify({"success": True, "cards": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json()
    try:
        cards = parse_card(data.get("dsl", ""))
        return jsonify({"valid": True, "card_count": len(cards)})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


# ---- Game API ----

@app.route("/api/game/state")
def api_game_state():
    return jsonify(_ser_state(_get_game()))


@app.route("/api/game/new", methods=["POST"])
def api_game_new():
    sid = secrets.token_hex(8)
    session["game_id"] = sid
    game = _build_game()
    _games[sid] = game
    return jsonify({"ok": True, **_ser_state(game)})


@app.route("/api/game/action", methods=["POST"])
def api_game_action():
    game = _get_game()
    data = request.get_json()
    action = data.get("action", "")
    msg = ""

    try:
        if action == "play_land":
            ok = game.play_land(0, data.get("card_id", ""))
            msg = "Land played" if ok else "Can't play land"

        elif action == "tap":
            ok = game.tap_land_for_mana(0, data.get("card_id", ""))
            msg = "Tapped for mana" if ok else "Can't tap"

        elif action == "cast":
            ok = game.cast_spell(
                0, data.get("card_id", ""),
                targets=data.get("targets") or None,
                x_value=data.get("x_value", 0),
                kicked=data.get("kicked", False),
            )
            msg = "Spell cast" if ok else "Can't cast (check mana/timing)"

        elif action == "resolve":
            if game.state.stack.is_empty:
                msg = "Stack is empty"
            else:
                result = game.resolve_top_of_stack()
                name = result["card_name"] if result else "?"
                msg = f"Resolved: {name}"
                if result and result.get("fizzled"):
                    msg += " (fizzled)"

        elif action == "attack":
            valid = game.declare_attackers(data.get("attacker_ids", []))
            msg = f"Attacking with {len(valid)} creature(s)"

        elif action == "block":
            valid = game.declare_blockers(data.get("blocks", {}))
            msg = f"{len(valid)} blocker(s) declared"

        elif action == "combat_damage":
            log = game.resolve_combat_damage()
            msg = "; ".join(log) if log else "No combat damage"

        elif action == "pass_priority":
            game.state.pass_priority()
            if len(game.state.players_passed) >= len(game.state.players):
                if not game.state.stack.is_empty:
                    result = game.resolve_top_of_stack()
                    msg = f"All passed. Resolved: {result['card_name']}" if result else "Resolved"
                else:
                    game.advance_step()
                    game.run_step()
                    msg = f"Advanced to {game.state.phase.name}/{game.state.step.name}"
            else:
                msg = "Priority passed"

        elif action == "next_step":
            game.advance_step()
            game.run_step()
            msg = f"Now: {game.state.phase.name}/{game.state.step.name}"

        elif action == "next_turn":
            game.advance_turn()
            game.state.phase, game.state.step = Phase.BEGINNING, Step.UNTAP
            game.run_step()
            game.advance_step()
            game.run_step()
            game.advance_step()
            msg = f"Turn {game.state.turn_number}: {game.state.active_player.name}"

        elif action == "cycle":
            ok = game.activate_cycling(0, data.get("card_id", ""))
            msg = "Cycled" if ok else "Can't cycle"

        else:
            msg = f"Unknown action: {action}"

    except Exception as e:
        msg = f"Error: {e}"

    return jsonify({"message": msg, **_ser_state(game)})


def main():
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
