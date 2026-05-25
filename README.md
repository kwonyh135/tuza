# tuza

Python-based automated Bitget futures trading bot.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

Fill `.env` with your Bitget and Telegram credentials before running.

## Strategy

- Symbol: `BTC/USDT:USDT`
- Timeframe: `1h`
- Leverage: `5x`
- Signal: SMA 60/80 crossover with ADX >= 25
- Stop loss: 3% price move
- Take profit: 26% price move

## Security

Do not commit real API keys or Telegram tokens. Keep them only in `.env` on the server.
