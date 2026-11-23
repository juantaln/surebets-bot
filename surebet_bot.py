#!/usr/bin/env python3
import requests
import time
import logging
from datetime import datetime
from config import (
    ODDS_API_KEY, ODDS_API_BASE,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    CAPITAL_POR_OP, MARGEN_MINIMO, DEPORTES, INTERVALO
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

alertas_enviadas = set()

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log.error(f"Error Telegram: {e}")
        return False

def obtener_odds(deporte):
    url = f"{ODDS_API_BASE}/sports/{deporte}/odds"
    params = {"apiKey": ODDS_API_KEY, "regions": "eu,uk", "markets": "h2h", "oddsFormat": "decimal"}
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        log.warning(f"Status {r.status_code} para {deporte}")
    except Exception as e:
        log.error(f"Error odds ({deporte}): {e}")
    return []

def analizar_partido(partido):
    casas = partido.get("bookmakers", [])
    if not casas:
        return None
    mejor = {}
    for casa in casas:
        for market in casa.get("markets", []):
            if market["key"] != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                n, o = outcome["name"], outcome["price"]
                if n not in mejor or o > mejor[n]["odd"]:
                    mejor[n] = {"odd": o, "casa": casa["title"]}
    outcomes = list(mejor.keys())
    if len(outcomes) < 2:
        return None
    odds_vals = [mejor[o]["odd"] for o in outcomes]
    suma_inv = sum(1/o for o in odds_vals)
    if suma_inv >= 1.0:
        return None
    margen = (1 - suma_inv) * 100
    if margen < MARGEN_MINIMO:
        return None
    total_inv = suma_inv
    stakes = [round(CAPITAL_POR_OP * (1/o) / total_inv) for o in odds_vals]
    ganancia = round(CAPITAL_POR_OP / suma_inv - CAPITAL_POR_OP)
    return {
        "partido": f"{partido.get('home_team')} vs {partido.get('away_team')}",
        "deporte": partido.get("sport_title", ""),
        "margen": round(margen, 2),
        "ganancia": ganancia,
        "apuestas": [{"outcome": outcomes[i], "odd": odds_vals[i], "casa": mejor[outcomes[i]]["casa"], "stake": stakes[i]} for i in range(len(outcomes))]
    }

def formatear_alerta(op):
    lineas = [
        f"🚨 <b>SUREBET DETECTADA</b> 🚨",
        f"",
        f"⚽ <b>{op['partido']}</b>",
        f"🏆 {op['deporte']}",
        f"",
        f"📈 <b>Margen: {op['margen']}%</b>",
        f"💰 <b>Ganancia: ${op['ganancia']:,} COP</b>",
        f"",
        f"<b>Apuestas:</b>",
    ]
    for ap in op["apuestas"]:
        lineas.append(f"  • <b>{ap['outcome']}</b> @ {ap['odd']} en {ap['casa']} → <b>${ap['stake']:,} COP</b>")
    lineas += [f"", f"💵 Capital: ${CAPITAL_POR_OP:,} COP", f"⏱ Ejecutar en menos de 10 min"]
    return "\n".join(lineas)

def escanear():
    log.info("Escaneando...")
    encontradas = 0
    for deporte in DEPORTES:
        partidos = obtener_odds(deporte)
        for partido in partidos:
            op = analizar_partido(partido)
            if op:
                clave = f"{op['partido']}_{op['margen']}"
                if clave not in alertas_enviadas:
                    if enviar_telegram(formatear_alerta(op)):
                        alertas_enviadas.add(clave)
                        log.info(f"✅ Alerta: {op['partido']} ({op['margen']}%)")
                        encontradas += 1
        if len(alertas_enviadas) > 500:
            alertas_enviadas.clear()
        time.sleep(1)
    if encontradas == 0:
        log.info("Sin surebets este ciclo.")

def main():
    log.info("SUREBETS BOT INICIADO")
    enviar_telegram(f"🤖 <b>Surebets Bot activo</b>\nEscaneando cada {INTERVALO//60} min\nCapital: ${CAPITAL_POR_OP:,} COP\nMargen mínimo: {MARGEN_MINIMO}%")
    while True:
        try:
            escanear()
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Error: {e}")
        time.sleep(INTERVALO)

if __name__ == "__main__":
    main()
