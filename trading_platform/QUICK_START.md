# Быстрый старт системы

## Текущий статус

✅ **Frontend**: http://localhost:5173 - работает
✅ **API**: http://localhost:8000 - работает (без Redis возвращает пустые данные)
⚠️ **Redis**: не запущен (нужен для получения данных)
⚠️ **Ingestors**: не запущены (нужны для получения данных с бирж)

## Почему нет данных?

Система показывает "Connected", но данных нет, потому что:

1. **Redis не запущен** - данные не могут быть сохранены и переданы
2. **Ingestors не запущены** - данные не поступают с бирж

## Решение: Запустить Redis и Ingestors

### Шаг 1: Запустить Redis

**Вариант A: Docker (самый простой)**
```bash
docker run -d -p 6379:6379 --name redis redis:latest
```

**Вариант B: WSL**
```bash
wsl
sudo apt install redis-server
sudo service redis-server start
```

**Вариант C: Windows Redis**
Скачайте и запустите: https://github.com/microsoftarchive/redis/releases

### Шаг 2: Перезапустить API (чтобы подключиться к Redis)

```powershell
# Остановить текущий API
Get-Process python | Where-Object {$_.CommandLine -like "*api*main.py*"} | Stop-Process

# Запустить заново
cd trading_platform
$env:PYTHONPATH = "C:\Users\HYPERPC\Documents\projects\trading-finance\trading_system\trading_platform"
python api\main.py --host 127.0.0.1 --port 8000 --redis redis://localhost:6379
```

### Шаг 3: Запустить Ingestor (для получения данных с Bybit)

```powershell
cd trading_platform
$env:PYTHONPATH = "C:\Users\HYPERPC\Documents\projects\trading-finance\trading_system\trading_platform"
python ingestors\bybit\main.py --redis redis://localhost:6379 --symbol BTCUSDT
```

### Шаг 4: Проверить

Откройте http://localhost:5173 - должны появиться данные:
- Orderbook (стакан заявок)
- Trades (сделки)
- Candles (свечи)
- Open Interest
- Liquidations

## Альтернатива: Тестовые данные

Если Redis недоступен, API будет работать, но возвращать пустые данные. Frontend покажет "Connected", но данных не будет.

## Проверка работы

1. **API работает?**
   ```powershell
   Invoke-WebRequest http://localhost:8000/dom/bybit/BTCUSDT
   ```

2. **Redis работает?**
   ```powershell
   python -c "import redis; r = redis.Redis.from_url('redis://localhost:6379'); print('Redis OK' if r.ping() else 'Redis FAIL')"
   ```

3. **Ingestor работает?**
   Проверьте вывод в консоли - должны быть сообщения о подключении к Bybit WebSocket.

## Структура системы

```
Frontend (5173) 
    ↕ WebSocket
API (8000)
    ↕ Redis Streams
Ingestors (bybit/binance/okx)
    ↕ WebSocket
Биржи (Bybit/Binance/OKX)
```

Без Redis и Ingestors система работает, но данных нет!
