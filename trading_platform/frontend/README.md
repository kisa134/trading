# Frontend — Orderflow Platform

Svelte + TypeScript + Vite. Минималистичный чёрный UI.

- **Слева:** DOM (стакан).
- **Центр:** Heatmap ордербука (Canvas 2D).
- **Снизу:** Footprint (бары bid/ask/delta).
- **Справа:** Tape (лента сделок) + Events (айсберги, стенки, spoof).

Запуск: из корня `trading_platform` выполнить `npm install` и `npm run dev` в папке `frontend`. По умолчанию подключается к API на `localhost:8000` (при dev на порту 5173 — прокси в vite.config не обязателен, используется прямой URL к 8000 для WebSocket).
