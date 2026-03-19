"""
🌙 Teste de conexao CLOB - rode no terminal antes do bot
python test_clob.py
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

PRIVATE_KEY       = os.getenv("PRIVATE_KEY", "")
POLY_SAFE_ADDRESS = os.getenv("POLY_SAFE_ADDRESS", "")

print(f"""
╔══════════════════════════════════════════════════╗
║   🌙 POLYMARKET - Teste de Conexao CLOB         ║
╚══════════════════════════════════════════════════╝
POLY_SAFE_ADDRESS : {POLY_SAFE_ADDRESS}
""")

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

    HOST = "https://clob.polymarket.com"

    # Tenta signature_type=2 (MetaMask proxy)
    print("Testando signature_type=2 (MetaMask proxy)...")
    client = ClobClient(
        HOST,
        key=PRIVATE_KEY,
        chain_id=137,
        signature_type=2,
        funder=POLY_SAFE_ADDRESS,
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    print("✅ Autenticado!\n")

    # Verifica balance e allowance
    params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
    result = client.get_balance_allowance(params)
    balance   = float(result.get("balance", 0)) / 1e6
    allowance = float(result.get("allowance", 0)) / 1e6
    print(f"  USDC Balance   : ${balance:.2f}")
    print(f"  USDC Allowance : ${allowance:.2f}")

    if allowance < 1:
        print("\n  ⚠️  Allowance muito baixo! Aprovando...")
        approval = client.update_balance_allowance(params)
        print(f"  ✅ Aprovado: {approval}")
    else:
        print("\n  ✅ Allowance OK — bot deve funcionar!")

    # Testa um market order simulado (busca dados do mercado atual)
    now = __import__('time').time()
    window_ts = int(now) - (int(now) % 300)
    slug = f"btc-updown-5m-{window_ts}"
    print(f"\n  Mercado atual: {slug}")

    import requests, json
    r = requests.get(f"https://gamma-api.polymarket.com/events?slug={slug}", timeout=10)
    if r.ok and r.json():
        mkt = r.json()[0]["markets"][0]
        outcomes = json.loads(mkt.get("outcomes", "[]"))
        clob_ids = json.loads(mkt.get("clobTokenIds", "[]"))
        print(f"  Outcomes     : {outcomes}")
        print(f"  Token IDs    : {[str(t)[:12]+'...' for t in clob_ids]}")
        print("\n  ✅ Tudo pronto! Reinicie o bot com rodar_limpo.bat")
    else:
        print(f"  ⚠️  Mercado {slug} não encontrado (pode ser fora do horário)")

except Exception as e:
    print(f"\n❌ Erro: {e}")
    print("\nVerifique:")
    print("  1. PRIVATE_KEY e POLY_SAFE_ADDRESS no .env")
    print("  2. Conexão com internet")
    print("  3. py-clob-client instalado: pip install py-clob-client")
