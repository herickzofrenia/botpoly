# ============================================================
#  🌙 POLYMARKET AI BOT - Configurações
#  Banca: $30 USDC
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

# ── Carteira Polymarket ──────────────────────────────────────
PRIVATE_KEY       = os.getenv("PRIVATE_KEY", "")
POLY_SAFE_ADDRESS = os.getenv("POLY_SAFE_ADDRESS", "")

# ── API Keys de IA ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Parâmetros do Monitor ────────────────────────────────────
ANALYSIS_INTERVAL    = 60
NEW_MARKETS_TRIGGER  = 1
MARKETS_TO_ANALYZE   = 10
TOP_PICKS_COUNT      = 3

# ── Regras de Aposta — calibrado para $30 de banca ──────────
BET_SIZE_USD       = 1.0    # sempre $1 por aposta
MAX_PER_MARKET_USD = 2.0    # máximo $2 por mercado (2 apostas)
MIN_CONFIDENCE     = 0.65

# ⚠️  TRADES REAIS ATIVADOS
DRY_RUN            = True

# ── Arquivos de Saída ────────────────────────────────────────
DATA_DIR        = "data"
MARKETS_CSV     = f"{DATA_DIR}/markets.csv"
PREDICTIONS_CSV = f"{DATA_DIR}/predictions.csv"
CONSENSUS_CSV   = f"{DATA_DIR}/consensus_picks.csv"
BETS_CSV        = f"{DATA_DIR}/bets.csv"

# ── URLs das APIs ─────────────────────────────────────────────
WS_URL        = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
CLOB_API_URL  = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# ── Prompt da IA ─────────────────────────────────────────────
ANALYSIS_SYSTEM_PROMPT = """You are an expert prediction market analyst for Bitcoin 5-minute markets on Polymarket.
Markets look like: "Bitcoin Up or Down - March 19, 9:50AM-9:55AM ET"
YES = Bitcoin goes UP in that 5-minute window
NO  = Bitcoin goes DOWN in that 5-minute window

Output ONLY valid JSON, nothing else. No markdown, no explanation outside JSON.

Analyze each market:
- If yes_price < 0.45 lean NO
- If yes_price > 0.55 lean YES
- If 0.45 <= yes_price <= 0.55 recommend NO_TRADE
- Consider the last trade direction as a signal

Respond with exactly this JSON:
{
  "markets": [
    {
      "question": "...",
      "recommendation": "YES" or "NO" or "NO_TRADE",
      "confidence": 0.0 to 1.0,
      "reasoning": "max 15 words"
    }
  ]
}"""
