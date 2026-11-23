"""Modelo y esfuerzo por agente y rol, con anulaciones locales opcionales."""
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ROLES = {"plan", "review", "code", "text", "research"}
AGENTES = {"codex", "claude", "agy"}
SIMPLE = re.compile(r"^[A-Za-z0-9._-]+$")

DEFAULTS = {
    "codex": {
        "code": ("gpt-6.2-sol", "medium"),
        "text": ("gpt-6.2-sol", "low"),
        "research": ("gpt-6.2-sol", "low"),
        "plan": ("gpt-6.2-sol", "medium"),
        "review": ("gpt-6.2-sol", "medium"),
    },
    "claude": {
        "plan": ("sonnet", "medium"),
        "review": ("sonnet", "medium"),
        "code": ("sonnet", "low"),
        "text": ("sonnet", "low"),
        "research": ("sonnet", "low"),
    },
    "agy": {
        "research": ("gemini-4-hydrogen", "medium"),
        "code": ("gemini-4-hydrogen", "medium"),
        "text": ("gemini-4-hydrogen", "medium"),
        "plan": ("gemini-4-neon", "medium"),
        "review": ("gemini-4-neon", "medium"),
    },
}


def elegir(agente, rol):
    """Devuelve la eleccion para el rol; ignora un modelos.json invalido."""
    base = DEFAULTS[agente][rol]
    try:
        data = json.loads((ROOT / "modelos.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return base
        for name, roles in data.items():
            if name not in AGENTES or not isinstance(roles, dict):
                return base
            for role, pair in roles.items():
                if (role not in ROLES or not isinstance(pair, list) or len(pair) != 2
                        or any(not isinstance(v, str) or not SIMPLE.fullmatch(v) for v in pair)):
                    return base
        return tuple(data.get(agente, {}).get(rol, base))
    except (OSError, ValueError, TypeError, RecursionError):
        return base
