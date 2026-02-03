<script lang="ts">
  import { formatPrice, formatSize, formatRelativeTime } from '../lib/format'
  export let trades: Array<{ side: string; price: number; size: number; ts: number }> = []
  const max = 80
  $: list = trades.slice(0, max)
  $: volBuy = list.filter(t => (t.side || '').toLowerCase().startsWith('b')).reduce((a, t) => a + t.size, 0)
  $: volSell = list.filter(t => !(t.side || '').toLowerCase().startsWith('b')).reduce((a, t) => a + t.size, 0)
</script>

<div class="tape">
  {#if list.length > 0}
    <div class="vol-summary">Buy: {formatSize(volBuy)} | Sell: {formatSize(volSell)}</div>
  {/if}
  {#each list as t}
    <div class="row" class:buy={(t.side || '').toLowerCase().startsWith('b')} class:sell={!(t.side || '').toLowerCase().startsWith('b')}>
      <span class="time" title={new Date(t.ts < 10_000_000_000 ? t.ts * 1000 : t.ts).toISOString()}>{formatRelativeTime(t.ts)}</span>
      <span class="price">{formatPrice(t.price)}</span>
      <span class="size">{formatSize(t.size)}</span>
    </div>
  {/each}
  {#if list.length === 0}
    <div class="empty">No trades. Данные появятся после подключения и поступления сделок.</div>
  {/if}
</div>

<style>
  .tape { padding: 4px; max-height: 200px; overflow-y: auto; font-size: 11px; }
  .vol-summary { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; padding: 2px 4px; }
  .row { display: grid; grid-template-columns: 48px 1fr auto; gap: 8px; align-items: center; padding: 2px 4px; }
  .row.buy { color: var(--buy); border-left: 2px solid var(--buy); }
  .row.sell { color: var(--sell); border-left: 2px solid var(--sell); }
  .time { font-size: 10px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .price { font-variant-numeric: tabular-nums; }
  .size { color: var(--text-muted); }
  .empty { color: var(--text-muted); padding: 8px; }
</style>
