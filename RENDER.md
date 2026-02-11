# Деплой на Render

## Почему деплой мог не сработать

1. **Репозиторий не подключён**  
   В [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint** укажите репозиторий `kisa134/trading` и ветку `main`. Либо подключите репозиторий к каждому сервису вручную.

2. **Нет авто-деплоя при push**  
   В настройках сервиса (или Blueprint) включите **Auto-Deploy**: **Settings** → **Build & Deploy** → **Auto-Deploy** = Yes. Тогда каждый push в `main` будет запускать сборку.

3. **Права GitHub App**  
   Если push не запускает деплой: [Установка Render GitHub App](https://github.com/apps/render/installations/new) — выберите нужный аккаунт и дайте доступ к репозиторию `trading`.

4. **Группа переменных**  
   В Blueprint используется группа `trading-env-5mux`. В Render Dashboard создайте **Environment Group** с именем `trading-env-5mux` и задайте переменные:
   - `REDIS_URL` (обязательно; например Redis из Render или Upstash)
   - `OPENROUTER_API_KEY`, `COLD_STORAGE_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — по необходимости

5. **Ручной деплой**  
   **Dashboard** → ваш сервис → **Manual Deploy** → **Deploy latest commit**.

## Что входит в render.yaml

Сейчас в Blueprint только сервисы, которые есть в репо:

- **trading-api** — FastAPI (WebSocket + REST)
- **trading-frontend** — статика (Vite/React) после `npm run build`
- Воркеры: **hot-storage**, **ingestor-bybit/binance/okx**, **cold-writer**, **graph-writer**, **tick-anomaly**, **celery-worker**, **celery-beat**

Воркеры из пакета `analytics` (tape_aggregator, iceberg_detector и др.) в конфиге отключены — такого пакета в репозитории пока нет. Когда появится — их можно снова добавить в `render.yaml`.

## После изменений

Сделайте коммит и push в `main`:

```bash
git add render.yaml RENDER.md
git commit -m "fix: render blueprint only existing services, add deploy doc"
git push origin main
```

Если авто-деплой включён, сборка на Render запустится сама. Иначе нажмите **Manual Deploy** в Dashboard.
