const isDev = typeof location !== 'undefined' && location.port === '5173'
const envApi = (import.meta as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ?? ''
// На Render: если VITE_API_URL не задан — выводим API из текущего хоста (trading-frontend-* → trading-api-*)
const derivedOnRender =
  typeof location !== 'undefined' && location.hostname.includes('onrender.com')
    ? location.protocol + '//' + location.hostname.replace(/trading-frontend/, 'trading-api')
    : ''
const API_ORIGIN = envApi || derivedOnRender
const API_WS = API_ORIGIN
  ? (API_ORIGIN.startsWith('https') ? 'wss:' : 'ws:') + '//' + new URL(API_ORIGIN).host + '/ws'
  : isDev
    ? `ws://${location.hostname}:8000/ws`
    : `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`

export function wsUrl(exchange: string, symbol: string, channels: string[]): string {
  const c = channels.join(',')
  return `${API_WS}?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(symbol)}&channels=${encodeURIComponent(c)}`
}

export const API_BASE =
  API_ORIGIN || (isDev ? `http://${location.hostname}:8000` : '')

export async function fetchDom(exchange: string, symbol: string) {
  const r = await fetch(`${API_BASE}/dom/${exchange}/${symbol}`)
  return r.json()
}

export async function fetchTrades(exchange: string, symbol: string, limit = 100) {
  const r = await fetch(`${API_BASE}/trades/${exchange}/${symbol}?limit=${limit}`)
  return r.json()
}

export async function fetchBybitSymbols() {
  const url = 'https://api.bybit.com/v5/market/instruments-info?category=linear'
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Bybit symbols request failed: ${r.status}`)
  const data = await r.json()
  const list = data?.result?.list || []
  return list.map((item: { symbol?: string }) => item.symbol).filter(Boolean)
}

export type Candle = {
  start: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  confirm: boolean
}

export async function fetchKline(
  exchange: string,
  symbol: string,
  interval = 1,
  limit = 500
): Promise<Candle[]> {
  const r = await fetch(
    `${API_BASE}/kline/${exchange}/${symbol}?interval=${interval}&limit=${limit}`
  )
  return r.json()
}

export type ImbalanceResponse = {
  current: { ts: number; imbalance_pct: number }
  history: Array<{ ts: number; imbalance_pct: number }>
}

export async function fetchImbalance(
  exchange: string,
  symbol: string,
  limit = 0
): Promise<ImbalanceResponse> {
  const r = await fetch(
    `${API_BASE}/imbalance/${exchange}/${symbol}?limit=${limit}`
  )
  return r.json()
}

export type SnapshotPayload = {
  exchange: string
  symbol: string
  imageBase64: string
  ts: number
  trigger?: 'timer' | 'volume_spike' | 'manual'
}

export type SnapshotResponse = {
  snapshotId: string
  ts: number
}

export type AiStatusResponse = { openrouter_configured: boolean }

export async function fetchAiStatus(): Promise<AiStatusResponse> {
  const r = await fetch(`${API_BASE}/ai/status`)
  if (!r.ok) return { openrouter_configured: false }
  return r.json()
}

export async function uploadSnapshot(payload: SnapshotPayload): Promise<SnapshotResponse> {
  const r = await fetch(`${API_BASE}/ai/snapshot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!r.ok) {
    const err = await r.text()
    throw new Error(err || `Snapshot upload failed: ${r.status}`)
  }
  return r.json()
}
