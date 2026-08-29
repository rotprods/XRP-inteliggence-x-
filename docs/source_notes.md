# Source Notes

The implementation boundaries were designed against official documentation families:

- XRP Ledger HTTP/WebSocket public methods and API versioning;
- Binance Spot public market-data API;
- Coinbase Exchange and Kraken public market-data APIs;
- FRED series observations and vintage-aware economic data.
- KuCoin Unified API public spot klines and service-status endpoints (read-only; XRP/BTC/ETH USDT only).

Endpoint contracts must be revalidated during live integration because provider APIs, symbols, rate limits and regional access can change.
