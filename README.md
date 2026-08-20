# Crypto DayTrader

Een eenvoudige crypto daytrading-dashboard voor **paper trading en backtesting**.

## Wat zit erin?
- Live Binance spot-koersdata
- Timeframes van 1m t/m 1h
- EMA 9/21/50
- RSI 14
- MACD
- Volume-filter
- Long-signaal bij een sterke combinatie van indicatoren
- Automatische stop-loss, take-profit en positieomvang
- Backtest op de laatste 500 candles
- Geen echte orders: veilig om mee te experimenteren

## Installeren

1. Installeer Python 3.11 of nieuwer.
2. Open een terminal in deze map.
3. Installeer:
   `pip install -r requirements.txt`
4. Start:
   `streamlit run app.py`

De browser opent daarna automatisch.

## Belangrijk
Dit is een eerste versie en plaatst **geen echte trades**. Backtests zijn geen garantie voor toekomstige resultaten. Voor een echte tradingbot zouden we eerst uitgebreidere backtesting, slippage/fees, short-posities, logging en API-beveiliging toevoegen.
