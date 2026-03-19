"""
🌙 POLYMARKET AI BOT - Agente v5
Estrategia baseada no artigo LunarResearcher:
  1. Expected Value (EV) > 5% para entrar
  2. Kelly Criterion (Quarter Kelly) para tamanho da aposta
  3. Claude API estima probabilidade real
  4. Log Returns para calcular lucro corretamente
"""

import json
import csv
import os
import math
import time
import requests
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic

import config
from monitor import load_markets, save_markets, append_predictions, append_consensus, log

ET = timezone(timedelta(hours=-4))

# ── Parametros ────────────────────────────────────────────────
EV_THRESHOLD    = 0.05   # Edge minimo de 5% para entrar
KELLY_FRACTION  = 0.25   # Quarter Kelly (conservador)
BANKROLL        = 30.0   # Banca inicial em USDC
MIN_BET         = 0.50   # Aposta minima
MAX_BET         = 5.00   # Aposta maxima por trade
CONFIDENCE_MIN  = "medium"  # Nao entra se Claude tiver confianca "low"

_claude = None
def get_claude():
    global _claude
    if _claude is None:
        _claude = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _claude


# ── Formula 1: Expected Value ─────────────────────────────────

def expected_value(market_price: float, true_prob: float) -> float:
    """
    EV = P(win) * Profit - P(lose) * Loss
    No Polymarket: compra YES a market_price, ganha (1 - market_price) se WIN
    """
    return true_prob * (1 - market_price) - (1 - true_prob) * market_price


# ── Formula 2: Kelly Criterion ────────────────────────────────

def kelly_fraction(true_prob: float, market_price: float) -> float:
    """
    f* = (p*b - q) / b
    b = payout ratio = (1 - market_price) / market_price
    """
    if market_price <= 0 or market_price >= 1:
        return 0
    b = (1 - market_price) / market_price
    p = true_prob
    q = 1 - true_prob
    f = (p * b - q) / b
    return max(f, 0) * KELLY_FRACTION  # Quarter Kelly


def position_size(true_prob: float, market_price: float, bankroll: float) -> float:
    """Calcula tamanho da posicao em USDC."""
    f = kelly_fraction(true_prob, market_price)
    size = bankroll * f
    return round(max(min(size, MAX_BET), MIN_BET if f > 0 else 0), 2)


# ── Formula 4: Log Return ─────────────────────────────────────

def log_return(price_start: float, price_end: float) -> float:
    if price_start <= 0 or price_end <= 0:
        return 0
    return math.log(price_end / price_start)

def expected_log_return(true_prob: float, market_price: float) -> float:
    """Retorno logaritmico esperado da posicao."""
    win_return  = math.log(1 / market_price)        # ganho se WIN
    loss_return = math.log(0.001 / market_price)    # perda se LOSS (~zero)
    return true_prob * win_return + (1 - true_prob) * loss_return


# ── Claude: Estimativa de Probabilidade ──────────────────────

def get_true_probability(market_question: str, market_price: float,
                          yes_price: float, no_price: float,
                          volume: str = "?", end_date: str = "?") -> tuple:
    """
    Pede ao Claude para estimar a probabilidade real do evento.
    Retorna (true_prob, confidence)
    """
    prompt = f"""You are a quantitative prediction market analyst.

Analyze this Polymarket market:
Question: {market_question}
Current YES price: {yes_price:.3f} ({yes_price*100:.1f}¢)
Current NO price:  {no_price:.3f} ({no_price*100:.1f}¢)
Volume: {volume}
Close date: {end_date}

Your task:
1. Estimate the REAL probability of YES (0.00 - 1.00)
2. Consider base rates for similar events
3. Factor in current market conditions and any news you know
4. Be calibrated - if you say 70%, 7 out of 10 similar assessments should be correct

For BTC 5-minute markets:
- These resolve based on whether BTC price at end > price at start of the 5-min window
- Consider recent momentum, volatility, and market microstructure

Respond STRICTLY in JSON:
{{"probability": 0.XX, "confidence": "high/medium/low", "reasoning": "one sentence max"}}"""

    try:
        resp = get_claude().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        prob = float(data.get("probability", 0.5))
        conf = data.get("confidence", "low")
        reason = data.get("reasoning", "")
        return prob, conf, reason
    except Exception as e:
        log(f"⚠️  Claude erro: {e}")
        return 0.5, "low", "erro"


# ── Preco atual do token ──────────────────────────────────────

def get_market_info(slug: str) -> dict:
    """Busca precos atuais e dados do mercado."""
    for attempt in range(3):
        try:
            r = requests.get(f"{config.GAMMA_API_URL}/events",
                params={"slug": slug}, timeout=15)
            if r.ok and r.json():
                event = r.json()[0]
                mkt   = event["markets"][0]
                outcomes  = json.loads(mkt.get("outcomes", "[]"))
                prices    = json.loads(mkt.get("outcomePrices", "[]"))
                clob_ids  = json.loads(mkt.get("clobTokenIds", "[]"))
                volume    = mkt.get("volume", "?")
                end_date  = mkt.get("endDate", "?")

                yes_price = no_price = None
                yes_id = no_id = None
                for i, outcome in enumerate(outcomes):
                    if outcome.lower() == "up":
                        yes_price = float(prices[i]) if i < len(prices) else None
                        yes_id    = str(clob_ids[i]) if i < len(clob_ids) else None
                    elif outcome.lower() == "down":
                        no_price  = float(prices[i]) if i < len(prices) else None
                        no_id     = str(clob_ids[i]) if i < len(clob_ids) else None

                return {
                    "yes_price": yes_price, "no_price": no_price,
                    "yes_id": yes_id, "no_id": no_id,
                    "volume": volume, "end_date": end_date
                }
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
    return {}


# ── Controle de apostas ───────────────────────────────────────

def load_bets():
    bets = {}
    if not os.path.exists(config.BETS_CSV): return bets
    with open(config.BETS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bets[row["condition_id"]] = float(row.get("total_bet_usd", 0))
    return bets

def save_bets(bets):
    with open(config.BETS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["condition_id", "total_bet_usd"])
        w.writeheader()
        for cid, total in bets.items():
            w.writerow({"condition_id": cid, "total_bet_usd": total})

def can_bet(cid, bets, size):
    return (config.MAX_PER_MARKET_USD - bets.get(cid, 0.0)) >= size

def register_bet(cid, bets, size):
    bets[cid] = bets.get(cid, 0.0) + size
    save_bets(bets)


# ── Trader ────────────────────────────────────────────────────

class PolymarketTrader:
    def __init__(self):
        self._clob  = None
        self._ready = False
        if config.PRIVATE_KEY and not config.DRY_RUN:
            self._init_clob()

    def _init_clob(self):
        try:
            from py_clob_client.client import ClobClient
            self._clob = ClobClient(
                config.CLOB_API_URL,
                key=config.PRIVATE_KEY,
                chain_id=137,
                signature_type=2,
                funder=config.POLY_SAFE_ADDRESS,
            )
            self._clob.set_api_creds(self._clob.create_or_derive_api_creds())
            self._ready = True
            log("✅ CLOB inicializado — trades reais ATIVOS")
        except Exception as e:
            log(f"⚠️  CLOB erro: {e}")

    def buy(self, token_id: str, size_usd: float, direction: str, price: float) -> dict:
        payout = (1/price - 1) * 100 if price > 0 else 0
        if config.DRY_RUN:
            log(f"🧪 [DRY RUN] {direction} ${size_usd:.2f} @ {price*100:.0f}¢ → payout: +{payout:.0f}%")
            return {"status": "dry_run"}
        if not self._ready:
            return {"status": "error"}
        try:
            from py_clob_client.clob_types import MarketOrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY
            order = self._clob.create_market_order(
                MarketOrderArgs(token_id=token_id, amount=size_usd, side=BUY))
            resp = self._clob.post_order(order, OrderType.FOK)
            log(f"✅ ORDEM: {resp}")
            return resp
        except Exception as e:
            log(f"❌ Trade erro: {e}")
            return {"status": "error"}


# ── Agente Principal ──────────────────────────────────────────

class AnalysisAgent:
    def __init__(self):
        self.trader            = PolymarketTrader()
        self._analyzed_windows = set()
        self._last_sleep_log   = 0

    def _parse_window_ts(self, market):
        url  = market.get("url", "")
        slug = url.split("/event/")[-1] if "/event/" in url else ""
        try:
            return int(slug.replace("btc-updown-5m-", ""))
        except:
            return 0

    def _get_slug(self, market):
        url = market.get("url", "")
        return url.split("/event/")[-1] if "/event/" in url else ""

    def _secs_to_close(self, window_ts):
        if window_ts == 0: return 9999
        now = int(datetime.now(timezone.utc).timestamp())
        return (window_ts + 300) - now

    async def run_analysis_cycle(self):
        markets  = load_markets(config.MARKETS_CSV)
        if not markets: return

        now_unix = int(datetime.now(timezone.utc).timestamp())
        bets     = load_bets()
        acted    = False

        active = []
        future = []
        for cid, market in markets.items():
            wts  = self._parse_window_ts(market)
            if wts == 0: continue
            secs = self._secs_to_close(wts)
            if wts > now_unix + 300:
                future.append((cid, market, wts, secs))
            elif secs > 0:
                active.append((cid, market, wts, secs))

        if not active:
            now = int(datetime.now(timezone.utc).timestamp())
            if now - self._last_sleep_log >= 60:
                if future:
                    _, nm, nts, _ = min(future, key=lambda x: x[2])
                    s = nts - now_unix
                    h, m, sc = s//3600, (s%3600)//60, s%60
                    log(f"💤 Próximo: {nm['question'][:45]} em {h:02d}h{m:02d}m{sc:02d}s")
                else:
                    log("💤 Nenhum mercado ativo")
                self._last_sleep_log = now
            return

        for cid, market, wts, secs in active:
            window_key = f"{cid}_{wts}"

            # Janela de entrada: T-30s a T-180s
            if secs > 180 or secs < 20:
                if not acted:
                    log(f"⏳ T-{secs}s | {market['question'][:55]}")
                    acted = True
                continue

            if window_key in self._analyzed_windows:
                if not acted:
                    log(f"⏳ T-{secs}s (analisado) | {market['question'][:50]}")
                    acted = True
                continue

            slug = self._get_slug(market)
            log(f"\n⏱️  T-{secs}s | ANALISANDO: {market['question']}")

            # ── Passo 1: Busca precos atuais ─────────────────────
            info = get_market_info(slug)
            if not info or info.get("yes_price") is None:
                log(f"  ⚠️  Nao conseguiu buscar precos")
                continue

            yes_price = info["yes_price"]
            no_price  = info["no_price"] or (1 - yes_price)

            log(f"  💰 UP={yes_price*100:.1f}¢  DOWN={no_price*100:.1f}¢")

            # ── Passo 2: Claude estima probabilidade real ─────────
            log(f"  🤖 Consultando Claude...")
            true_prob, confidence, reasoning = get_true_probability(
                market_question=market["question"],
                market_price=yes_price,
                yes_price=yes_price,
                no_price=no_price,
                volume=str(info.get("volume", "?")),
                end_date=str(info.get("end_date", "?"))
            )

            log(f"  🧠 Claude: prob={true_prob:.0%} | conf={confidence} | {reasoning[:60]}")

            # Ignora se confiança baixa
            if confidence == "low":
                self._analyzed_windows.add(window_key)
                log(f"  ⏭️  Confiança baixa — passando")
                continue

            # ── Passo 3: Calcula EV para YES e NO ────────────────
            ev_yes = expected_value(yes_price, true_prob)
            ev_no  = expected_value(no_price, 1 - true_prob)

            # Decide qual lado tem edge
            if ev_yes > ev_no and ev_yes > EV_THRESHOLD:
                direction  = "UP"
                token_id   = info.get("yes_id")
                mkt_price  = yes_price
                ev         = ev_yes
                true_p     = true_prob
            elif ev_no > ev_yes and ev_no > EV_THRESHOLD:
                direction  = "DOWN"
                token_id   = info.get("no_id")
                mkt_price  = no_price
                ev         = ev_no
                true_p     = 1 - true_prob
            else:
                self._analyzed_windows.add(window_key)
                log(f"  ⏭️  EV insuficiente — YES={ev_yes:.1%} NO={ev_no:.1%} (min {EV_THRESHOLD:.0%})")
                continue

            # ── Passo 4: Kelly Criterion ──────────────────────────
            size   = position_size(true_p, mkt_price, BANKROLL)
            f_frac = kelly_fraction(true_p, mkt_price)
            elr    = expected_log_return(true_p, mkt_price)
            payout = (1/mkt_price - 1) * 100

            if size < MIN_BET:
                self._analyzed_windows.add(window_key)
                log(f"  ⏭️  Kelly muito pequeno (${size:.2f}) — passando")
                continue

            if not can_bet(cid, bets, size):
                log(f"  ⛔ Limite de ${config.MAX_PER_MARKET_USD:.0f} atingido")
                continue

            # ── Resultado final ───────────────────────────────────
            print(f"""
  ┌─────────────────────────────────────────┐
  │  🎯 SINAL: {'🟢 BUY ' + direction:<32}│
  │  Market prob  : {mkt_price*100:.1f}¢              │
  │  Claude prob  : {true_p*100:.1f}%              │
  │  Edge (EV)    : {ev*100:.1f}% por dolar       │
  │  Kelly (¼)    : {f_frac*100:.1f}% da banca       │
  │  Aposta       : ${size:.2f} USDC           │
  │  Payout pot.  : +{payout:.0f}%               │
  │  Log Return   : {elr:.4f}               │
  │  Razao        : {reasoning[:40]:<40}│
  └─────────────────────────────────────────┘""")

            self._analyzed_windows.add(window_key)

            # Executa
            result = self.trader.buy(
                token_id=token_id or "",
                size_usd=size,
                direction=direction,
                price=mkt_price
            )

            if result.get("status") != "error":
                register_bet(cid, bets, size)

            append_consensus([{
                "timestamp":      datetime.now(ET).strftime("%Y-%m-%d %H:%M ET"),
                "rank":           1,
                "condition_id":   cid,
                "question":       market["question"],
                "recommendation": "YES" if direction == "UP" else "NO",
                "confidence":     round(ev, 3),
                "reasoning":      f"Preco={mkt_price*100:.0f}c EV={ev*100:.1f}% Claude={true_p*100:.0f}% Kelly={f_frac*100:.1f}% Payout={payout:.0f}%",
                "url":            market.get("url", ""),
                "bet_usd":        size,
            }], config.CONSENSUS_CSV)

            append_predictions([{
                "timestamp":      datetime.now(ET).strftime("%Y-%m-%d %H:%M ET"),
                "condition_id":   cid,
                "question":       market["question"],
                "recommendation": "YES" if direction == "UP" else "NO",
                "confidence":     round(ev, 3),
                "reasoning":      f"Preco={mkt_price*100:.0f}c EV={ev*100:.1f}% Claude={true_p:.0%} Payout={payout:.0f}%",
            }], config.PREDICTIONS_CSV)
