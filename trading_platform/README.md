# Trading Platform (Orderflow)

Платформа ордерфлоу: ingestors → Redis Streams → hot storage → analytics → API → frontend.

**Фаза 3 — Cold storage:** PostgreSQL (см. `storage/cold_schema.sql`). Запуск writer: `COLD_STORAGE_URL=postgresql://... python -m storage.cold --redis redis://localhost:6379`. REST история: `/history/trades/`, `/history/heatmap/`, `/history/footprint/`, `/history/events/` (при наличии COLD_STORAGE_URL в API читают из БД).

## Фаза 1 — Ядро

**Требования:** Redis, Python 3.11+

1. Установить зависимости:
   ```bash
   cd trading_platform
   pip install -r requirements.txt
   ```

2. Запустить Redis (локально или Docker):
   ```bash
   redis-server
   # или: docker run -p 6379:6379 redis:7
   ```

3. В трёх терминалах запустить:
   - **Hot storage** (читает потоки, пишет DOM и кольцевые буферы в Redis):
     ```bash
     python -m storage.hot --redis redis://localhost:6379
     ```
   - **Bybit ingestor** (REST snapshot + WebSocket → Redis Streams):
     ```bash
     python -m ingestors.bybit.main --redis redis://localhost:6379 --symbol BTCUSDT
     ```
   - **API** (WebSocket + REST):
     ```bash
     python -m api.main --redis redis://localhost:6379 --port 8000
     ```

4. Подключение к API:
   - WebSocket: `ws://localhost:8000/ws?exchange=bybit&symbol=BTCUSDT&channels=orderbook_realtime,trades_realtime`
   - REST DOM: `GET /dom/bybit/BTCUSDT`
   - REST trades: `GET /trades/bybit/BTCUSDT?limit=100`
   - Health: `GET /health`

**Фаза 2 — Analytics (в отдельных терминалах):**
- Tape aggregator: `python -m analytics.tape_aggregator --redis redis://localhost:6379`
- Iceberg detector: `python -m analytics.iceberg_detector --exchange bybit --symbol BTCUSDT`
- Wall/spoof detector: `python -m analytics.wall_spoof_detector --exchange bybit --symbol BTCUSDT`
- Heatmap/footprint: `python -m analytics.heatmap_footprint_aggregator --exchange bybit --symbol BTCUSDT`

WebSocket каналы: `orderbook_realtime`, `trades_realtime`, `heatmap_stream`, `footprint_stream`, `events_stream`.
REST: `/dom/`, `/trades/`, `/heatmap/`, `/footprint/`, `/events/`, `/tape/`.

Запуск из корня репозитория:
```bash
cd trading_platform
python -m storage.hot
# в других терминалах:
python -m ingestors.bybit.main
python -m api.main
# опционально analytics:
python -m analytics.iceberg_detector
python -m analytics.heatmap_footprint_aggregator
```

**Фаза 4 — Frontend:** Svelte + TypeScript в `frontend/`. Запуск: `cd frontend && npm install && npm run dev`. Открыть http://localhost:5173. UI: DOM слева, heatmap по центру, footprint снизу, tape и события справа.

**Фаза 5 — Мультибиржа:** Ingestors для Binance и OKX в том же формате. Запуск:
- Binance: `python -m ingestors.binance.main --redis redis://localhost:6379 --symbol BTCUSDT`
- OKX: `python -m ingestors.okx.main --redis redis://localhost:6379 --symbol BTCUSDT`
Во фронте в подвале можно выбрать биржу (Bybit / Binance / OKX) и символ.
