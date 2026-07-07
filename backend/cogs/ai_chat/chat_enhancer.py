import re
import ast
import operator
import random
import asyncio
from time import time
from typing import Dict, Any
from datetime import datetime, timezone

from ..database.firebase_setup import db

# ═══════════════════════════════════════════════════════
# LOCAL TOOLS (zero-cost, no API call)
# ═══════════════════════════════════════════════════════

# Simple math ops
MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_MATH_PATTERN = re.compile(
    r"(?:hitung|itung|kalkulasi|calculate?|berapa\s+)?"
    r"(\d[\d\s+\-*/().,%^]*)",
    re.IGNORECASE,
)

_CONVERT_UNITS = r"(cm|centimeter|m|meter|km|kilometer|kg|kilogram|g|gram|mg|milligram|liter|ml|milliliter|inch|inches|foot|feet|yard|mile|pound|lbs|oz|ounce|\u00b0C|\u00b0F)"
_CONVERT_PATTERN = re.compile(
    rf"(\d+[.]?\d*)\s*{_CONVERT_UNITS}\s*(?:ke|to|->|>)\s*{_CONVERT_UNITS}",
    re.IGNORECASE,
)

_DICE_PATTERN = re.compile(r"(?:roll(?:\s+dice)?|lempar(?:\s+dadu)?|dadu)\s*(\d*)", re.IGNORECASE)

_UNIT_CONVERSIONS = {
    ("cm", "m"): 0.01, ("m", "cm"): 100.0,
    ("m", "km"): 0.001, ("km", "m"): 1000.0,
    ("kg", "g"): 1000.0, ("g", "kg"): 0.001,
    ("kg", "mg"): 1_000_000.0, ("mg", "kg"): 0.000001,
    ("liter", "ml"): 1000.0, ("ml", "liter"): 0.001,
    ("inch", "cm"): 2.54, ("cm", "inch"): 0.393701,
    ("foot", "m"): 0.3048, ("m", "foot"): 3.28084,
    ("yard", "m"): 0.9144, ("m", "yard"): 1.09361,
    ("mile", "km"): 1.60934, ("km", "mile"): 0.621371,
    ("pound", "kg"): 0.453592, ("kg", "pound"): 2.20462,
    ("oz", "g"): 28.3495, ("g", "oz"): 0.035274,
}


def _safe_expr_eval(expr: str) -> str:
    try:
        expr = expr.strip().replace(",", "").replace("x", "*").replace("÷", "/").replace("^", "**")
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Expression, ast.Expr, ast.BinOp, ast.UnaryOp, ast.Constant, *MATH_OPS.keys())):
                if isinstance(node, ast.Load):
                    continue
                return ""
        result = eval(compile(tree, "", "eval"), {"__builtins__": {}}, {})
        if isinstance(result, (int, float)):
            return f"{result:g}"
    except Exception:
        pass
    return ""


_UNIT_ALIASES = {
    "centimeter": "cm", "centimeters": "cm",
    "meter": "m", "meters": "m",
    "kilometer": "km", "kilometers": "km",
    "kilogram": "kg", "kilograms": "kg",
    "gram": "g", "grams": "g",
    "milligram": "mg", "milligrams": "mg",
    "milliliter": "ml", "milliliters": "ml",
    "inch": "inch", "inches": "inch",
    "foot": "foot", "feet": "foot",
    "yard": "yard", "yards": "yard",
    "mile": "mile", "miles": "mile",
    "pound": "pound", "lbs": "pound",
    "ounce": "oz", "ounces": "oz",
}


def _normalize_unit(u: str) -> str:
    u = u.lower()
    return _UNIT_ALIASES.get(u, u)


def _run_convert(text: str) -> str:
    m = _CONVERT_PATTERN.search(text)
    if not m:
        return ""
    try:
        val = float(m.group(1))
        from_u = _normalize_unit(m.group(2))
        to_u = _normalize_unit(m.group(3))
    except (ValueError, IndexError):
        return ""
    if from_u in ("°c",) and to_u in ("°f",):
        result = val * 9 / 5 + 32
        return f"{val}°C = {result:g}°F"
    if from_u in ("°f",) and to_u in ("°c",):
        result = (val - 32) * 5 / 9
        return f"{val}°F = {result:g}°C"
    key = (from_u, to_u)
    if key in _UNIT_CONVERSIONS:
        result = val * _UNIT_CONVERSIONS[key]
        return f"{val:g} {from_u} = {result:g} {to_u}"
    return ""


def _run_math(text: str) -> str:
    m = _MATH_PATTERN.search(text)
    if not m:
        return ""
    expr = m.group(1).strip()
    # Skip bare numbers (e.g. years like "2026") — they're not math
    if expr.isdigit() or re.match(r"^\d+$", expr):
        return ""
    result = _safe_expr_eval(expr)
    if result:
        return f"{expr} = {result}"
    return ""


def _run_dice(text: str) -> str:
    m = _DICE_PATTERN.search(text)
    if not m:
        return ""
    sides_str = m.group(1)
    sides = int(sides_str) if sides_str and sides_str.isdigit() else 6
    if sides < 2:
        sides = 6
    result = random.randint(1, sides)
    return f"Dadu d{sides}: {result}"


TOOL_REGISTRY = [
    ("dice", _run_dice),
    ("convert", _run_convert),
    ("math", _run_math),
]


def run_tools(user_message: str) -> str:
    for name, handler in TOOL_REGISTRY:
        result = handler(user_message)
        if result:
            return f"[TOOL:{name}] {result}"
    return ""


# ═══════════════════════════════════════════════════════
# USER PREFERENCES — Firestore
# ═══════════════════════════════════════════════════════

PREFS_COLLECTION = "guild_settings"

_PREFS_CACHE: Dict[str, tuple] = {}
_PREFS_TTL = 60  # seconds


async def get_user_prefs(guild_id: str, user_id: str) -> Dict[str, Any]:
    key = f"prefs:{guild_id}:{user_id}"
    now = time()
    cached = _PREFS_CACHE.get(key)
    if cached and cached[1] > now:
        return cached[0]
    if db is None:
        return {}
    try:
        doc_ref = (
            db.collection(PREFS_COLLECTION)
            .document(str(guild_id))
            .collection("ai_user_prefs")
            .document(str(user_id))
        )
        doc = await asyncio.to_thread(doc_ref.get)
        if doc.exists:
            data = doc.to_dict()
            _PREFS_CACHE[key] = (data, now + _PREFS_TTL)
            return data
    except Exception:
        pass
    return {}


async def save_user_pref(guild_id: str, user_id: str, key: str, value: Any) -> None:
    if db is None:
        return
    try:
        doc_ref = (
            db.collection(PREFS_COLLECTION)
            .document(str(guild_id))
            .collection("ai_user_prefs")
            .document(str(user_id))
        )
        def _blocking():
            doc_ref.set({key: value, "updated_at": datetime.now(timezone.utc)}, merge=True)
        await asyncio.to_thread(_blocking)
        _PREFS_CACHE.pop(f"prefs:{guild_id}:{user_id}", None)
    except Exception:
        pass


_INFORMAL_WORDS = {
    "gua", "lu", "lo", "elu", "gue", "gw", "luu", "kagak", "nggak", "gak",
    "doang", "sih", "dah", "deh", "dong", "kok", "yo", "wkwk", "wkwkwk",
    "anjir", "anjay", "bgt", "banget", "nih", "tuh", "yaudah", "udah",
}

_FORMAL_WORDS = {
    "saya", "anda", "kami", "kita", "terima kasih", "mohon", "silakan",
    "maaf", "permisi", "apakah", "bagaimana", "mengapa",
}


def _estimate_formality(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 0.5
    informal_count = sum(1 for w in words if w in _INFORMAL_WORDS)
    formal_count = sum(1 for w in words if w in _FORMAL_WORDS)
    total = informal_count + formal_count
    if total == 0:
        return 0.5
    return formal_count / total


async def update_user_style_prefs(guild_id: str, user_id: str, user_msg: str, assistant_msg: str) -> None:
    if db is None:
        return
    try:
        old = await get_user_prefs(guild_id, user_id)
        old_formality = old.get("formality_level", 0.5)
        new_estimate = _estimate_formality(user_msg)
        smoothed = (old_formality * 0.7) + (new_estimate * 0.3)

        doc_ref = (
            db.collection(PREFS_COLLECTION)
            .document(str(guild_id))
            .collection("ai_user_prefs")
            .document(str(user_id))
        )
        def _blocking():
            doc_ref.set({
                "formality_level": smoothed,
                "last_interaction": datetime.now(timezone.utc),
            }, merge=True)
        await asyncio.to_thread(_blocking)
        _PREFS_CACHE.pop(f"prefs:{guild_id}:{user_id}", None)
    except Exception:
        pass


def enhance_server_context(server_ctx: str, intent_instructions: str, user_prefs: Dict[str, Any]) -> str:
    parts = []

    if intent_instructions:
        parts.append(intent_instructions.strip())

    formality = user_prefs.get("formality_level")
    if formality is not None:
        if formality < 0.3:
            parts.append("Catatan: User ini cenderung santai - gunakan gaya bahasa kasual yang natural.")
        elif formality > 0.7:
            parts.append("Catatan: User ini cenderung formal - gunakan bahasa yang sopan dan terstruktur.")

    if parts:
        return "\n".join(parts) + "\n\n" + server_ctx

    return server_ctx
