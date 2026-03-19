"""
🌙 POLYMARKET AI BOT - Monitor
Busca mercados BTC 5min diretamente pelo slug calculado (timestamp atual).
A API /events?active=true não retorna esses mercados — precisamos buscar por slug.
"""

import asyncio
import json
import csv
import os
import requests
import websockets
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import config

ET = timezone(timedelta(hours=-4))

def log(msg: str):
    ts = datetime.now(ET).strftime("%H:%M:%S ET")
    print(f"[{ts}] {msg}")


def ensure_data_dir():
    os.makedirs(config.DATA_DIR, exist_ok=True)


MARKETS_FIELDS = ["condition_id", "question", "url", "yes_price", "no_price",
                  "volume_usd", "last_trade_size", "last_trade_side",
                  "last_seen", "analyzed"]


def load_markets(path: str) -> dict:
    markets = {}
    if not os.path.exists(path):
        return markets
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            markets[row["condition_id"]] = row
    return markets


def save_markets(markets: dict, path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MARKETS_FIELDS)
        writer.writeheader()
        for m in markets.values():
            writer.writerow({k: m.get(k, "") for k in MARKETS_FIELDS})


def append_predictions(predictions: list, path: str):
    file_exists = os.path.exists(path)
    fields = ["timestamp", "condition_id", "question", "recommendation", "confidence", "reasoning"]
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for p in predictions:
            writer.writerow(p)


def append_consensus(picks: list, path: str):
    file_exists = os.path.exists(path)
    fields = ["timestamp", "rank", "condition_id", "question",
              "recommendation", "confidence", "reasoning", "url", "bet_usd"]
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for p in picks:
            writer.writerow(p)


def get_current_window_ts() -> int:
    """Timestamp de início da janela de 5min atual."""
    now = int(datetime.now(timezone.utc).timestamp())
    return now - (now % 300)


def fetch_btc_markets(markets_db: dict) -> int:
    """
    Busca os mercados BTC 5min pelo slug calculado diretamente.
    Busca a janela atual + as próximas 3 (para ter tempo de preparar a análise).
    """
    added = updated = 0
    now = int(datetime.now(timezone.utc).timestamp())
    current_ts = now - (now % 300)

    # Busca janela atual + próximas 3 (atual, +5min, +10min, +15min)
    for offset in [0, 300, 600, 900]:
        window_ts = current_ts + offset
        slug = f"btc-updown-5m-{window_ts}"

        try:
            resp = requests.get(
                f"{config.GAMMA_API_URL}/events",
                params={"slug": slug},
                timeout=8,
            )
            if not resp.ok:
                continue

            events = resp.json()
            if not events:
                continue

            event = events[0]
            if not event.get("active") or event.get("closed"):
                continue

            title = event.get("title", "")

            for m in event.get("markets", []):
                cid      = m.get("conditionId", "")
                question = m.get("question", "") or title
                if not cid:
                    continue

                tokens = m.get("tokens", [])
                yes_price = no_price = ""
                for t in tokens:
                    outcome = (t.get("outcome") or "").lower()
                    if outcome in ("yes", "up"):
                        yes_price = str(t.get("price", ""))
                    elif outcome in ("no", "down"):
                        no_price = str(t.get("price", ""))

                if cid not in markets_db:
                    markets_db[cid] = {
                        "condition_id": cid,
                        "question":     question,
                        "url":          f"https://polymarket.com/event/{slug}",
                        "yes_price":    yes_price,
                        "no_price":     no_price,
                        "volume_usd":   str(m.get("volume", "")),
                        "last_trade_size": "",
                        "last_trade_side": "",
                        "last_seen":    datetime.now(ET).strftime("%m/%d %H:%M ET"),
                        "analyzed":     "false",
                    }
                    added += 1
                    log(f"  🆕 {question}")
                else:
                    if yes_price:
                        markets_db[cid]["yes_price"] = yes_price
                    if no_price:
                        markets_db[cid]["no_price"] = no_price
                    markets_db[cid]["last_seen"] = datetime.now(ET).strftime("%m/%d %H:%M ET")
                    updated += 1

        except Exception as e:
            log(f"⚠️  Erro ao buscar {slug}: {e}")

    if added:
        log(f"✅ {added} novos | {updated} atualizados")
    return added + updated


class PolymarketMonitor:
    def __init__(self):
        ensure_data_dir()
        self.markets: dict = load_markets(config.MARKETS_CSV)
        self.stats = defaultdict(int)
        self.ws_connected = False
        log(f"✅ {len(self.markets)} mercados carregados")

    def _process_trade(self, data: dict):
        cid   = data.get("asset_id") or data.get("conditionId", "")
        price = float(data.get("price", 0) or 0)
        size  = float(data.get("size", 0) or data.get("usdcSize", 0) or 0)
        side  = data.get("side", "")
        if not cid or cid not in self.markets:
            return
        size_usd = size * price if size < 1_000 else size
        m = self.markets[cid]
        m["last_trade_size"] = str(size_usd)
        m["last_trade_side"] = side
        m["last_seen"] = datetime.now(ET).strftime("%m/%d %H:%M ET")
        if side.upper() in ("BUY", "UP"):
            m["yes_price"] = str(price)
        elif side.upper() in ("SELL", "DOWN"):
            m["no_price"]  = str(price)
        self.stats["ws_trades"] += 1

    def print_status(self):
        print(f"""
📊 Status @ {datetime.now(ET).strftime('%H:%M:%S ET')}
{'='*55}
WebSocket  : {'✅ Conectado' if self.ws_connected else '❌ Desconectado'}
WS updates : {self.stats['ws_trades']:,} atualizacoes de preco
Mercados   : {len(self.markets):,} monitorados
{'='*55}""")

    async def run_ws(self):
        log(f"📡 Busca inicial | {datetime.now(ET).strftime('%H:%M:%S ET')}")
        fetch_btc_markets(self.markets)
        save_markets(self.markets, config.MARKETS_CSV)

        while True:
            try:
                log("🔌 Conectando ao WebSocket...")
                async with websockets.connect(
                    config.WS_URL, ping_interval=20, ping_timeout=10,
                    additional_headers={"User-Agent": "polymarket-ai-bot/1.0"},
                ) as ws:
                    self.ws_connected = True
                    log(f"✅ WebSocket conectado | {datetime.now(ET).strftime('%H:%M:%S ET')}")
                    await ws.send(json.dumps({"type": "market", "assets_ids": []}))
                    async for raw in ws:
                        try:
                            msgs = json.loads(raw)
                            if isinstance(msgs, list):
                                for m in msgs:
                                    self._process_trade(m)
                            elif isinstance(msgs, dict):
                                self._process_trade(msgs)
                        except json.JSONDecodeError:
                            pass
            except websockets.ConnectionClosed:
                self.ws_connected = False
                log("⚠️  WS desconectado — reconectando em 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                self.ws_connected = False
                log(f"❌ WS erro: {e} — reconectando em 10s...")
                await asyncio.sleep(10)
