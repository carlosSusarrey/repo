"""Flask web application for card design and game simulation."""

from __future__ import annotations

import os

from flask import Flask, render_template, request, jsonify
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.exceptions import NotFound

from functools import partial

from mtg_engine.dsl import parse_card
from mtg_engine.dsl.llm_parser import translate_rules_text_llm, get_available_models, generate_card_dsl, LLMParseError


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
        # Build type expression from types/exclude_types (new format)
        types = tgt.get("types")
        if types:
            exclude_types = tgt.get("exclude_types", [])
            type_parts = list(types) + [f"!{et}" for et in exclude_types]
            type_expr = " | ".join(type_parts)
        else:
            # Fallback: old target_type key
            type_expr = tgt.get("target_type", "?")
        parts = [type_expr]
        ctrl = tgt.get("controller")
        if ctrl:
            parts.append(ctrl)
        state = tgt.get("state")
        if state:
            parts.append(state)
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
    use_llm = data.get("use_llm", False)
    llm_model = data.get("llm_model", "mistral:latest")

    try:
        translate_fn = None
        if use_llm:
            translate_fn = partial(translate_rules_text_llm, model=llm_model)
        cards = parse_card(dsl_text, translate_fn=translate_fn)
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


@app.route("/api/ai-models")
def api_ai_models():
    """Return available Ollama models."""
    models = get_available_models()
    return jsonify({
        "available": len(models) > 0,
        "models": [{"name": m["name"], "size": m.get("size", 0)} for m in models],
    })


@app.route("/api/ai-parse", methods=["POST"])
def api_ai_parse():
    """Parse rules text directly using LLM (standalone, no DSL wrapper needed)."""
    data = request.get_json()
    rules_text = data.get("rules_text", "")
    model = data.get("model", "mistral:latest")

    if not rules_text.strip():
        return jsonify({"success": False, "error": "No rules text provided"}), 400

    try:
        result = translate_rules_text_llm(rules_text, model=model)
        source = result.pop("_source", "llm")
        model_used = result.pop("_model", model)

        # Build translation strings
        translations = []
        for kw in sorted(result.get("keywords", set()), key=lambda k: k.name):
            translations.append({"category": "keyword", "dsl": f"keywords: {kw.name.lower()}"})
        for effect in result.get("effects", []):
            translations.append({"category": "effect", "dsl": f"effect: {_effect_to_dsl(effect)}"})
        for trig in result.get("triggered_abilities", []):
            effects_dsl = "; ".join(_effect_to_dsl(e) for e in trig.get("effects", []))
            translations.append({"category": "trigger", "dsl": f"when({trig.get('trigger')}): {effects_dsl}"})
        for act in result.get("activated_abilities", []):
            cost = act.get("cost", {})
            cost_str = cost.get("mana", "{0}")
            if cost.get("tap"):
                cost_str = f"{cost_str}, {{T}}" if cost_str != "{0}" else "{T}"
            if cost.get("is_loyalty"):
                lc = cost.get("loyalty_cost", 0)
                cost_str = f"{'+' if lc > 0 else ''}{lc}"
            effects_dsl = "; ".join(_effect_to_dsl(e) for e in act.get("effects", []))
            translations.append({"category": "activated", "dsl": f"activate({cost_str}): {effects_dsl}"})

        return jsonify({
            "success": True,
            "translations": translations,
            "source": source,
            "model": model_used,
            "keywords": [kw.name.lower() for kw in result.get("keywords", set())],
            "effects": result.get("effects", []),
            "triggered_abilities": result.get("triggered_abilities", []),
            "activated_abilities": result.get("activated_abilities", []),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai-generate", methods=["POST"])
def api_ai_generate():
    """Generate complete card DSL from a natural language description."""
    data = request.get_json()
    description = data.get("description", "")
    model = data.get("model", "mistral:latest")

    if not description.strip():
        return jsonify({"success": False, "error": "No description provided"}), 400

    try:
        dsl = generate_card_dsl(description, model=model)

        # Try to parse the generated DSL to validate it
        parse_error = None
        cards = []
        try:
            parsed = parse_card(dsl)
            for card in parsed:
                card_data = {
                    "name": card.name,
                    "type": card.card_type.name,
                    "cost": str(card.cost),
                    "rules_text": card.rules_text,
                }
                if card.is_creature:
                    card_data["power"] = card.power
                    card_data["toughness"] = card.toughness
                if card.loyalty is not None:
                    card_data["loyalty"] = card.loyalty
                cards.append(card_data)
        except Exception as e:
            parse_error = str(e)

        return jsonify({
            "success": True,
            "dsl": dsl,
            "model": model,
            "valid": parse_error is None,
            "parse_error": parse_error,
            "cards": cards,
        })
    except LLMParseError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def main():
    prefix = os.environ.get('SCRIPT_NAME', '')
    if prefix:
        application = DispatcherMiddleware(NotFound(), {prefix: app})
        from werkzeug.serving import run_simple
        run_simple('0.0.0.0', 5000, application, use_debugger=True, use_reloader=True)
    else:
        app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
