const isDev = typeof location !== 'undefined' && location.port === '5173'
const API_ORIGIN = (import.meta as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ?? ''
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
