# Trading Platform

Платформа для получения и визуализации данных с криптобирж: ingestors → Redis Streams → hot storage → API → frontend.

## Архитектура

```
Биржи (Bybit/Binance/OKX)
    ↓ [WebSocket + REST]
Ingestors (нормализация)
    ↓ [Redis Streams]
Hot Storage (DOM, кольцевые буферы)
    ↓
API (FastAPI + WebSocket)
    ↓
Frontend (Svelte)
```

## Требования

- Redis
- Python 3.11+
- Node.js 18+ (для фронтенда)

## Установка

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

## Запуск

### Backend

В отдельных терминалах запустить:

1. **Hot storage** (читает потоки, пишет DOM и кольцевые буферы в Redis):
   ```bash
   python -m storage.hot --redis redis://localhost:6379
   ```

2. **Ingestors** (выберите одну или несколько бирж):
   ```bash
   # Bybit
   python -m ingestors.bybit.main --redis redis://localhost:6379 --symbol BTCUSDT
   
   # Binance
   python -m ingestors.binance.main --redis redis://localhost:6379 --symbol BTCUSDT
   
   # OKX
   python -m ingestors.okx.main --redis redis://localhost:6379 --symbol BTCUSDT
   ```

3. **API** (WebSocket + REST):
   ```bash
   python -m api.main --redis redis://localhost:6379 --port 8000
   ```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Открыть http://localhost:5173

## API

### WebSocket

Подключение: `ws://localhost:8000/ws?exchange=bybit&symbol=BTCUSDT&channels=orderbook_realtime,trades_realtime,kline,open_interest,liquidations`

Каналы:
- `orderbook_realtime` — обновления стакана
- `trades_realtime` — сделки
- `kline` — свечи
- `open_interest` — открытый интерес
- `liquidations` — ликвидации

### REST Endpoints

- `GET /health` — статус API
- `GET /dom/{exchange}/{symbol}` — текущий DOM
- `GET /trades/{exchange}/{symbol}?limit=100` — последние сделки
- `GET /kline/{exchange}/{symbol}?interval=1&limit=500` — свечи
- `GET /oi/{exchange}/{symbol}?limit=100` — открытый интерес
- `GET /liquidations/{exchange}/{symbol}?limit=100` — ликвидации

## Данные

### Bybit
- Orderbook (snapshot + delta)
- Trades
- Kline (OHLCV)
- Open Interest
- Liquidations

### Binance
- Orderbook (snapshot + delta)
- Trades (aggTrade)
- Liquidations (forceOrder)
- Open Interest (REST polling)

### OKX
- Orderbook (snapshot + delta)
- Trades
- Open Interest

## Frontend

Интерфейс с вкладками для каждой биржи:
- **Левая панель**: Orderbook (DOM) с накопительным объемом
- **Центральная панель**: График свечей с overlay сделок
- **Правая панель**: Метрики (OI, последняя цена), таблица сделок, ликвидации

## Опционально: Cold Storage

Для долгосрочного хранения данных в PostgreSQL:

```bash
COLD_STORAGE_URL=postgresql://user:pass@localhost:5432/db python -m storage.cold --redis redis://localhost:6379
```

REST история: `/history/trades/{exchange}/{symbol}` (при наличии COLD_STORAGE_URL читает из БД).
