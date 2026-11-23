"""Conteos locales de consumo; no estima los limites de las suscripciones."""
import json
import math
import time
from pathlib import Path


def numero(value, entero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return value >= 0 and (not entero or isinstance(value, int))


def limpiar_uso(uso):
    if not isinstance(uso, dict):
        return {}
    return {k: uso[k] for k in ("tokens_in", "tokens_out", "tokens_total", "costo_usd")
            if numero(uso.get(k), entero=k != "costo_usd")}


def leer_uso(path):
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if (not isinstance(row, dict) or not numero(row.get("ts"))
                        or row.get("agente") not in ("codex", "claude", "agy")):
                    continue
                yield row
    except OSError:
        return


def resumen(rows):
    agents = {}
    for row in rows:
        totals = agents.setdefault(row["agente"], dict(llamadas=0, tokens=0, segundos=0, limites=0))
        totals["llamadas"] += 1
        totals["tokens"] += limpiar_uso(row).get("tokens_total", 0)
        if numero(row.get("segundos")):
            totals["segundos"] += row["segundos"]
        totals["limites"] += row.get("kind") == "limit"
    return agents


def reporte_consumo(path):
    lines = ["", "## Consumo", "",
             "| Agente | Llamadas | Tokens totales | Tiempo total (s) | Limites de cuota |",
             "|---|---:|---:|---:|---:|"]
    for agent, r in sorted(resumen(leer_uso(path)).items()):
        lines.append(f"| {agent} | {r['llamadas']} | {r['tokens']} | {r['segundos']:.2f} | {r['limites']} |")
    lines += ["", "Tokens reportados por las CLIs; los datos ausentes no se estiman."]
    return lines


def main_uso(runs_dir=None, ahora=None):
    if runs_dir is None:
        from .core import ROOT
        runs_dir = ROOT / "runs"
    ahora = time.time() if ahora is None else ahora
    rows = [row for path in sorted(Path(runs_dir).glob("*/uso.jsonl")) for row in leer_uso(path)]
    ventanas = [resumen(row for row in rows if ahora - hours * 3600 <= row["ts"] <= ahora)
                for hours in (5, 7 * 24)]
    total = resumen(rows)
    print("Agente | 5h llamadas / tokens | 7d llamadas / tokens | Total llamadas / tokens")
    for agent in sorted(total):
        cells = [f"{v.get(agent, {}).get('llamadas', 0)} / {v.get(agent, {}).get('tokens', 0)}"
                 for v in [*ventanas, total]]
        print(agent + " | " + " | ".join(cells))
    if not total:
        print("Sin consumo registrado.")
    print("Son conteos locales: no incluyen el uso fuera de Codex Max (por ejemplo, el chat del jefe con Claude).")
    print("Tokens ausentes no se estiman; estos conteos no indican la cuota disponible del plan.")
