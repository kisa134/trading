/**
 * Единое форматирование цен, объёмов и времени для всех панелей.
 */

export function formatPrice(price: number, decimals = 2): string {
  const fixed = price.toFixed(decimals)
  const [intPart, decPart] = fixed.split('.')
  const withSpaces = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  return decPart != null ? `${withSpaces}.${decPart}` : withSpaces
}

export function formatSize(size: number, decimals = 2): string {
  return size.toFixed(decimals)
}

const normalizeTs = (ts: number) => (ts < 10_000_000_000 ? ts * 1000 : ts)

export function formatTime(ts: number): string {
  const d = new Date(normalizeTs(ts))
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function formatRelativeTime(ts: number, now = Date.now()): string {
  const t = normalizeTs(ts)
  const sec = Math.floor((now - t) / 1000)
  if (sec < 5) return 'now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const h = Math.floor(min / 60)
  return `${h}h ago`
}
