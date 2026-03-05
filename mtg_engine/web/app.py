"""Flask web application for card design and game simulation."""

from __future__ import annotations

from flask import Flask, render_template, request, jsonify

from mtg_engine.dsl import parse_card


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


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
            }
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
