FROM node:20-alpine AS build
WORKDIR /app
COPY trading_platform/frontend/package.json /app/package.json
COPY trading_platform/frontend/svelte.config.js /app/svelte.config.js
COPY trading_platform/frontend/tsconfig.json /app/tsconfig.json
COPY trading_platform/frontend/vite.config.ts /app/vite.config.ts
COPY trading_platform/frontend/index.html /app/index.html
COPY trading_platform/frontend/src /app/src
RUN npm install && npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app/dist /app/dist
RUN npm install -g serve
ENV PORT=3000
CMD ["sh", "-c", "serve -s dist -l $PORT"]
