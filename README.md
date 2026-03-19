# 🌙 PolyMarket AI Bot

Bot automatizado para trading no Polymarket — mercados **Bitcoin Up or Down (5 minutos)**.

## Estratégia

Baseada no artigo [LunarResearcher](https://x.com/LunarResearcher) — 4 fórmulas matemáticas:

1. **Expected Value (EV)** — só entra quando edge > 5%
2. **Kelly Criterion (¼ Kelly)** — tamanho da aposta proporcional à banca
3. **Claude API** — estima a probabilidade real do evento
4. **Log Returns** — calcula lucro sem distorção aritmética

## Arquivos

| Arquivo | Descrição |
|---|---|
| `main.py` | Ponto de entrada — 3 tasks paralelas |
| `agent.py` | Agente de análise e execução |
| `monitor.py` | WebSocket + busca de mercados |
| `config.py` | Configurações gerais |
| `dashboard.py` | Dashboard de performance |

## Setup

```bash
# 1. Clonar
git clone https://github.com/herickzofrenia/botpoly.git
cd botpoly

# 2. Ambiente virtual
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 3. Dependências
pip install -r requirements.txt

# 4. Credenciais
cp .env.example .env
# edite o .env com suas chaves

# 5. Configurar allowance (1x apenas)
python test_clob.py

# 6. Rodar
python main.py
```

## Configuração (.env)

```env
PRIVATE_KEY=0x...          # Private key da MetaMask
POLY_SAFE_ADDRESS=0x...    # Endereço proxy wallet Polymarket
ANTHROPIC_API_KEY=sk-ant-... # Chave da API Claude
```

## Parâmetros (config.py)

```python
DRY_RUN   = True    # False para trades reais
BET_SIZE  = 1.0     # Tamanho base da aposta (USDC)
MAX_BET   = 5.0     # Aposta máxima por trade (Kelly)
EV_MIN    = 0.05    # Edge mínimo de 5%
```

## Aviso

> Trading envolve risco de perda total. Use apenas capital que pode perder.
> Este bot é experimental — não é conselho financeiro.
