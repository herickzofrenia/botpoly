# ============================================================
#  POLYMARKET AI BOT - Configuracoes
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

PRIVATE_KEY       = os.getenv("PRIVATE_KEY", "")
POLY_SAFE_ADDRESS = os.getenv("POLY_SAFE_ADDRESS", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

ANALYSIS_INTERVAL    = 60
NEW_MARKETS_TRIGGER  = 1
MARKETS_TO_ANALYZE   = 10
TOP_PICKS_COUNT      = 3

BET_SIZE_USD       = 1.0
MAX_PER_MARKET_USD = 5.0   # limite POR MERCADO (cada janela de 5min e independente)
MIN_CONFIDENCE     = 0.65
DRY_RUN            = True

DATA_DIR        = "data"
MARKETS_CSV     = f"{DATA_DIR}/markets.csv"
PREDICTIONS_CSV = f"{DATA_DIR}/predictions.csv"
CONSENSUS_CSV   = f"{DATA_DIR}/consensus_picks.csv"
BETS_CSV        = f"{DATA_DIR}/bets.csv"

WS_URL        = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
CLOB_API_URL  = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"

ANALYSIS_SYSTEM_PROMPT = ""
