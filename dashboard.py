"""
🌙 POLYMARKET AI BOT - Dashboard de Performance
Mostra: preco de entrada → preco de saida (cashout) e payout
"""

import csv
import os
import time
import json
import requests
from datetime import datetime, timezone, timedelta

import config

ET = timezone(timedelta(hours=-4))
BANCA_INICIAL = 30.00


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def load_csv(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_result(pick: dict) -> dict:
    """
    Consulta API para ver resultado do mercado.
    Retorna: status, winner, entry_price, exit_price, payout_str
    """
    url = pick.get("url", "")
    slug = url.split("/event/")[-1] if "/event/" in url else ""
    rec  = pick.get("recommendation", "").upper()
    bet  = float(pick.get("bet_usd") or config.BET_SIZE_USD)

    # Extrai preco de entrada do reasoning
    entry_price = 0.0
    reasoning = pick.get("reasoning", "")
    try:
        for part in reasoning.split():
            if part.startswith("Claude=") or "%" in part:
                pass
            if "¢" in part:
                entry_price = float(part.replace("¢","").replace("Preco=","")) / 100
                break
        if entry_price == 0:
            # tenta extrair do campo confidence como EV
            conf = float(pick.get("confidence", 0))
            # se conf parece ser EV (0.0-1.0), nao e preco
    except:
        pass

    if not slug:
        return {"status": "PENDING", "winner": "?", "entry_c": 0,
                "exit_c": 0, "pnl": 0.0, "payout_str": "?"}

    try:
        r = requests.get(f"{config.GAMMA_API_URL}/events",
            params={"slug": slug}, timeout=8)
        if not r.ok or not r.json():
            return {"status": "PENDING", "winner": "?", "entry_c": 0,
                    "exit_c": 0, "pnl": 0.0, "payout_str": "?"}

        mkt    = r.json()[0]["markets"][0]
        closed = mkt.get("closed") or mkt.get("resolved")

        # Pega precos atuais
        outcomes   = json.loads(mkt.get("outcomes", "[]"))
        out_prices = json.loads(mkt.get("outcomePrices", "[]"))

        current_yes = current_no = 0.5
        for i, o in enumerate(outcomes):
            if o.lower() == "up":
                current_yes = float(out_prices[i]) if i < len(out_prices) else 0.5
            elif o.lower() == "down":
                current_no = float(out_prices[i]) if i < len(out_prices) else 0.5

        # Preco atual do lado apostado
        current_price = current_yes if rec == "YES" else current_no
        exit_c = round(current_price * 100)

        if not closed:
            payout_str = f"{exit_c}¢ (aberto)"
            return {"status": "PENDING", "winner": "?", "entry_c": round(entry_price*100),
                    "exit_c": exit_c, "pnl": 0.0, "payout_str": payout_str}

        # Mercado fechado — acha vencedor
        winner = "?"
        win_price = 0.0
        for i, price in enumerate(out_prices):
            if float(price) >= 0.99:
                winner = "YES" if outcomes[i].lower() == "up" else "NO"
                win_price = float(price)
                break

        if winner == "?":
            return {"status": "PENDING", "winner": "?", "entry_c": round(entry_price*100),
                    "exit_c": 100, "pnl": 0.0, "payout_str": "?"}

        if winner == rec:
            # WIN: recebeu $1 por share, pagou entry_price
            pnl = (1.0 - entry_price) * (bet / entry_price) if entry_price > 0 else bet * 0.9
            pnl = round(pnl, 2)
            entry_c = round(entry_price * 100) if entry_price > 0 else "?"
            payout_str = f"{entry_c}¢ → 100¢ (+{round((1/entry_price-1)*100) if entry_price>0 else '?'}%)"
            return {"status": "WIN", "winner": winner, "entry_c": entry_c,
                    "exit_c": 100, "pnl": pnl, "payout_str": payout_str}
        else:
            pnl = -bet
            entry_c = round(entry_price * 100) if entry_price > 0 else "?"
            payout_str = f"{entry_c}¢ → 0¢ (-100%)"
            return {"status": "LOSS", "winner": winner, "entry_c": entry_c,
                    "exit_c": 0, "pnl": pnl, "payout_str": payout_str}

    except Exception as e:
        return {"status": "PENDING", "winner": "?", "entry_c": 0,
                "exit_c": 0, "pnl": 0.0, "payout_str": f"erro: {str(e)[:20]}"}


def calcular_stats(picks: list) -> dict:
    resultados = []
    total_apostado = 0.0
    total_pnl      = 0.0
    wins = losses = pending = 0

    for p in picks:
        bet = float(p.get("bet_usd") or config.BET_SIZE_USD)
        res = check_result(p)

        if res["status"] == "WIN":
            wins += 1
        elif res["status"] == "LOSS":
            losses += 1
        else:
            pending += 1

        total_apostado += bet
        total_pnl      += res["pnl"]

        resultados.append({
            "timestamp":   p.get("timestamp", "")[:16].replace("T", " "),
            "rec":         p.get("recommendation", ""),
            "bet":         f"${bet:.2f}",
            "payout_str":  res["payout_str"],
            "status":      res["status"],
            "pnl":         f"${res['pnl']:+.2f}",
            "mercado":     p.get("question", "")[:42],
        })

    banca_atual   = BANCA_INICIAL + total_pnl
    roi           = (total_pnl / total_apostado * 100) if total_apostado > 0 else 0
    assertividade = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    return {
        "resultados":     resultados,
        "wins":           wins,
        "losses":         losses,
        "pending":        pending,
        "total_apostado": total_apostado,
        "total_pnl":      total_pnl,
        "banca_atual":    banca_atual,
        "roi":            roi,
        "assertividade":  assertividade,
    }


def render(stats: dict):
    clear()
    now  = datetime.now(ET).strftime("%d/%m/%Y %H:%M:%S ET")
    b    = stats["banca_atual"]
    g    = stats["total_pnl"]
    roi  = stats["roi"]
    acc  = stats["assertividade"]
    sg   = "+" if g >= 0 else ""
    sr   = "+" if roi >= 0 else ""

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║       🌙 POLYMARKET AI BOT — DASHBOARD DE PERFORMANCE           ║
║       {now:<57}║
╠══════════════════════════════════════════════════════════════════╣
║  💰 Banca Inicial : ${BANCA_INICIAL:<10.2f}                               ║
║  💼 Banca Atual   : ${b:<10.2f}  ({sg}${abs(g):.2f} / ROI: {sr}{roi:.1f}%)              ║
╠══════════════════════════════════════════════════════════════════╣
║  ✅ Wins : {stats['wins']:<5}  ❌ Losses : {stats['losses']:<5}  ⏳ Pendentes : {stats['pending']:<5}     ║
║  🎯 Assertividade : {acc:.1f}%  |  💵 Total apostado : ${stats['total_apostado']:.2f}          ║
╚══════════════════════════════════════════════════════════════════╝
""")

    if not stats["resultados"]:
        print("  Nenhuma aposta registrada ainda.\n")
        return

    # Cabeçalho
    print(f"  {'HORÁRIO':<17} {'DIR':<5} {'APOSTA':<7} {'ENTRADA→SAIDA':<22} {'STATUS':<8} {'P&L'}")
    print("  " + "─" * 80)

    for r in reversed(stats["resultados"][-20:]):
        icon = {"WIN": "✅", "LOSS": "❌", "PENDING": "⏳"}.get(r["status"], "?")
        print(f"  {r['timestamp']:<17} {r['rec']:<5} {r['bet']:<7} {r['payout_str']:<22} {icon}{r['status']:<7} {r['pnl']}")

    print()
    if config.DRY_RUN:
        print("  ⚠️  DRY RUN — simulação. Para trades reais: DRY_RUN = False no config.py\n")


def main():
    print("🌙 Dashboard — atualizando a cada 30s | Ctrl+C para sair\n")
    time.sleep(1)
    while True:
        try:
            picks = load_csv(config.CONSENSUS_CSV)
            stats = calcular_stats(picks) if picks else {
                "resultados": [], "wins": 0, "losses": 0, "pending": 0,
                "total_apostado": 0.0, "total_pnl": 0.0,
                "banca_atual": BANCA_INICIAL, "roi": 0.0, "assertividade": 0.0,
            }
            render(stats)
        except KeyboardInterrupt:
            print("\n👋 Dashboard encerrado.")
            break
        except Exception as e:
            print(f"\n⚠️  Erro: {e}")
        time.sleep(30)


if __name__ == "__main__":
    main()
