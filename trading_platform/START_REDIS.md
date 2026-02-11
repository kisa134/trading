# Как запустить Redis для работы системы

## Вариант 1: Docker (рекомендуется)

```bash
docker run -d -p 6379:6379 --name redis redis:latest
```

## Вариант 2: WSL (Windows Subsystem for Linux)

```bash
wsl
sudo apt update
sudo apt install redis-server
sudo service redis-server start
```

## Вариант 3: Установка Redis для Windows

1. Скачайте Redis для Windows: https://github.com/microsoftarchive/redis/releases
2. Распакуйте и запустите `redis-server.exe`

## Проверка

После запуска Redis проверьте подключение:

```bash
python -c "import redis; r = redis.Redis.from_url('redis://localhost:6379'); r.ping(); print('Redis OK')"
```

## Запуск системы

После запуска Redis:

1. **API сервер:**
   ```bash
   cd trading_platform
   python api/main.py --host 0.0.0.0 --port 8000 --redis redis://localhost:6379
   ```

2. **Ingestor (для получения данных с биржи):**
   ```bash
   cd trading_platform
   python ingestors/bybit/main.py --redis redis://localhost:6379 --symbol BTCUSDT
   ```

3. **Frontend:**
   ```bash
   cd trading_platform/frontend
   npm run dev
   ```

Без Redis API будет работать, но данные не будут поступать.
