"""
🌙 POLYMARKET AI BOT — Ponto de entrada
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from monitor import PolymarketMonitor, fetch_btc_markets, save_markets, log
from agent import AnalysisAgent
import config

ET = timezone(timedelta(hours=-4))

def now_et():
    return datetime.now(ET).strftime("%m/%d/%Y %H:%M:%S ET")

def print_banner():
    modo = "DRY RUN (simulacao)" if config.DRY_RUN else "REAL — cuidado!"
    print(f"""
+==============================================================+
|         POLYMARKET AI BOT -- by Moon Dev Style              |
+==============================================================+
|  Foco     : Bitcoin Up or Down (5 minutos)                  |
|  Metodo   : Analise Tecnica Binance (7 indicadores)         |
|  Entrada  : T-90s a T-15s antes do fechamento               |
|  Aposta   : $1.00 | Max $2.00 por mercado                   |
|  Modo     : {modo:<48}|
|  Horario  : {now_et():<48}|
+==============================================================+
""")

async def wait_for_next_minute():
    now = datetime.now(timezone.utc)
    secs = 60 - now.second
    if secs < 3:
        secs += 60
    next_time = (datetime.now(ET) + timedelta(seconds=secs)).strftime("%H:%M:%S ET")
    log(f"⏳ Sincronizando... iniciando em {secs}s ({next_time})")
    for remaining in range(secs, 0, -1):
        print(f"\r  Iniciando em {remaining:2d}s...", end="", flush=True)
        await asyncio.sleep(1)
    print("\r  ✅ Sincronizado!                    ")

async def run_bot():
    print_banner()
    await wait_for_next_minute()
    print_banner()
    log(f"🚀 Bot iniciado | {now_et()}")

    monitor = PolymarketMonitor()
    agent   = AnalysisAgent()

    # Task 1: WebSocket (preços RT)
    async def ws_task():
        await monitor.run_ws()

    # Task 2: Refresh de mercados — sincronizado no :00 de cada minuto
    async def refresh_task():
        while True:
            now = datetime.now(timezone.utc)
            sleep = 60 - now.second
            if sleep < 1:
                sleep = 1
            await asyncio.sleep(sleep)
            log(f"🔄 Refresh | {datetime.now(ET).strftime('%H:%M:%S ET')}")
            fetch_btc_markets(monitor.markets)
            save_markets(monitor.markets, config.MARKETS_CSV)
            monitor.print_status()

    # Task 3: Análise técnica — roda a cada 5s, INDEPENDENTE do WebSocket
    async def analysis_task():
        log(f"🤖 Análise técnica a cada 5s | {now_et()}")
        while True:
            try:
                await agent.run_analysis_cycle()
            except Exception as e:
                log(f"⚠️  Erro análise: {e}")
            await asyncio.sleep(5)

    await asyncio.gather(ws_task(), refresh_task(), analysis_task())

def run_status():
    import csv
    markets = {}
    if os.path.exists(config.MARKETS_CSV):
        with open(config.MARKETS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                markets[row["condition_id"]] = row
    total_bet = 0.0
    if os.path.exists(config.BETS_CSV):
        with open(config.BETS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                total_bet += float(row.get("total_bet_usd", 0))
    picks = 0
    if os.path.exists(config.CONSENSUS_CSV):
        with open(config.CONSENSUS_CSV, newline="", encoding="utf-8") as f:
            picks = sum(1 for _ in csv.DictReader(f))
    print(f"""
STATUS | {now_et()}
{'='*50}
Mercados monitorados : {len(markets):,}
Apostas registradas  : {picks:,}
Total apostado       : ${total_bet:.2f} USDC
{'='*50}""")

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--status":
        run_status()
    else:
        asyncio.run(run_bot())
