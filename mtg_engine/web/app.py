"""Flask web application for card design and game simulation."""

from __future__ import annotations

from flask import Flask, render_template, request, jsonify

from mtg_engine.dsl import parse_card


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


def _effect_to_dsl(effect: dict) -> str:
    """Convert an effect dict back to human-readable DSL notation."""
    t = effect.get("type", "")
    target = effect.get("target", {})

    def _fmt_target(tgt: dict) -> str:
        kind = tgt.get("kind", "")
        if kind == "self":
            return "self"
        if kind == "each_opponent":
            return "each_opponent"
        tt = tgt.get("target_type", "?")
        parts = [tt]
        ctrl = tgt.get("controller")
        if ctrl:
            parts.append(ctrl)
        state = tgt.get("state")
        if state:
            parts.append(f"state={state}")
        qualifier = kind if kind in ("target", "all") else "target"
        return f"{qualifier}({', '.join(parts)})"

    if t == "damage":
        return f"damage({_fmt_target(target)}, {effect.get('amount')})"
    if t == "x_damage":
        return f"x_damage({_fmt_target(target)})"
    if t == "draw":
        return f"draw({effect.get('amount')})"
    if t == "gain_life":
        return f"gain_life({effect.get('amount')})"
    if t == "lose_life":
        return f"lose_life({_fmt_target(target)}, {effect.get('amount')})"
    if t == "destroy":
        return f"destroy({_fmt_target(target)})"
    if t == "exile":
        return f"exile({_fmt_target(target)})"
    if t == "bounce":
        return f"bounce({_fmt_target(target)})"
    if t == "counter":
        return f"counter({_fmt_target(target)})"
    if t == "tap":
        return f"tap({_fmt_target(target)})"
    if t == "pump":
        p, th = effect.get("power", 0), effect.get("toughness", 0)
        return f"pump({_fmt_target(target)}, {p:+d}/{th:+d})"
    if t == "add_keyword":
        return f"add_keyword({_fmt_target(target)}, {effect.get('keyword')})"
    if t == "add_mana":
        return f"add_mana({effect.get('color')})"
    if t == "add_counter":
        return f"add_counter({_fmt_target(target)}, \"{effect.get('counter_type')}\", {effect.get('amount')})"
    if t == "mill":
        return f"mill({effect.get('amount')})"
    if t == "scry":
        return f"scry({effect.get('amount')})"
    if t == "create_token":
        return f"create_token(\"{effect.get('name')}\", {effect.get('power')}/{effect.get('toughness')})"
    if t == "sacrifice":
        return f"sacrifice({_fmt_target(target)})"
    return str(effect)


@app.route("/api/parse", methods=["POST"])
def api_parse():
    """Parse card DSL and return structured card data."""
    data = request.get_json()
    dsl_text = data.get("dsl", "")

    try:
        cards = parse_card(dsl_text)
        result = []
        for card in cards:
            card_data = {
                "name": card.name,
                "type": card.card_type.name,
                "cost": str(card.cost),
                "cmc": card.cost.converted_mana_cost,
                "colors": [c.name for c in card.colors],
                "rules_text": card.rules_text,
                "effects": card.effects,
                "keywords": [kw.name.lower() for kw in card.keywords] if card.keywords else [],
                "triggered_abilities": card.triggered_abilities or [],
                "activated_abilities": card.activated_abilities or [],
            }
            # Build DSL translations for the visual breakdown
            translations = []
            for kw in sorted(card.keywords, key=lambda k: k.name) if card.keywords else []:
                translations.append({
                    "category": "keyword",
                    "dsl": f"keywords: {kw.name.lower()}",
                })
            for effect in card.effects or []:
                translations.append({
                    "category": "effect",
                    "dsl": f"effect: {_effect_to_dsl(effect)}",
                })
            for trig in card.triggered_abilities or []:
                effects_dsl = "; ".join(_effect_to_dsl(e) for e in trig.get("effects", []))
                translations.append({
                    "category": "trigger",
                    "dsl": f"when({trig.get('trigger')}): {effects_dsl}",
                })
            for act in card.activated_abilities or []:
                cost = act.get("cost", {})
                cost_str = cost.get("mana", "{0}")
                if cost.get("tap"):
                    cost_str = f"{cost_str}, {{T}}" if cost_str != "{0}" else "{T}"
                effects_dsl = "; ".join(_effect_to_dsl(e) for e in act.get("effects", []))
                translations.append({
                    "category": "activated",
                    "dsl": f"activate({cost_str}): {effects_dsl}",
                })
            card_data["translations"] = translations

            if card.supertypes:
                card_data["supertypes"] = [s.name for s in card.supertypes]
            if card.subtypes:
                card_data["subtypes"] = card.subtypes
            if card.is_creature:
                card_data["power"] = card.power
                card_data["toughness"] = card.toughness
            if card.loyalty is not None:
                card_data["loyalty"] = card.loyalty
            result.append(card_data)

        return jsonify({"success": True, "cards": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/validate", methods=["POST"])
def api_validate():
    """Validate card DSL syntax without full parsing."""
    data = request.get_json()
    dsl_text = data.get("dsl", "")

    try:
        cards = parse_card(dsl_text)
        return jsonify({"valid": True, "card_count": len(cards)})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


def main():
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
