<script lang="ts">
  import { formatTime } from '../lib/format'

  export let trades: Array<{ side: string; price: number; size: number; ts: number; trade_id?: string }> = []
  export let maxTrades: number = 100
  export let filterSide: 'all' | 'buy' | 'sell' = 'all'

  $: filteredTrades = trades
    .filter(t => {
      if (filterSide === 'all') return true
      if (filterSide === 'buy') return (t.side || '').toLowerCase() === 'buy'
      return (t.side || '').toLowerCase() === 'sell'
    })
    .slice(0, maxTrades)

  function formatPrice(price: number): string {
    return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  function formatSize(size: number): string {
    if (size >= 1000) return size.toFixed(2)
    if (size >= 1) return size.toFixed(4)
    return size.toFixed(6)
  }
</script>

<div class="trades">
  <div class="trades-header">
    <div class="header-col">Time</div>
    <div class="header-col">Price</div>
    <div class="header-col">Size</div>
    <div class="header-col">Side</div>
  </div>
  <div class="trades-body">
    {#each filteredTrades as trade}
      <div class="row" class:buy={(trade.side || '').toLowerCase() === 'buy'} class:sell={(trade.side || '').toLowerCase() === 'sell'}>
        <div class="col time">{formatTime(trade.ts)}</div>
        <div class="col price">{formatPrice(trade.price)}</div>
        <div class="col size">{formatSize(trade.size)}</div>
        <div class="col side">{trade.side || '—'}</div>
      </div>
    {/each}
    {#if filteredTrades.length === 0}
      <div class="empty">No trades</div>
    {/if}
  </div>
</div>

<style>
  .trades {
    display: flex;
    flex-direction: column;
    font-family: 'Courier New', monospace;
    font-size: 11px;
    color: var(--text, #e0e0e0);
    background: var(--bg-panel, #0a0a0a);
  }

  .trades-header {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 0.8fr;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border, #333);
    font-weight: 600;
    font-size: 10px;
    color: var(--text-muted, #888);
  }

  .trades-body {
    display: flex;
    flex-direction: column;
    max-height: 400px;
    overflow-y: auto;
  }

  .row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 0.8fr;
    padding: 3px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    transition: background 0.1s;
  }

  .row:hover {
    background: rgba(255, 255, 255, 0.05);
  }

  .row.buy {
    background: rgba(16, 185, 129, 0.05);
  }

  .row.sell {
    background: rgba(239, 68, 68, 0.05);
  }

  .col {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .col.time {
    text-align: left;
    color: var(--text-muted, #888);
  }

  .col.price {
    color: var(--text, #e0e0e0);
  }

  .col.size {
    color: var(--text, #e0e0e0);
  }

  .col.side {
    font-weight: 600;
  }

  .row.buy .col.side {
    color: var(--buy, #10b981);
  }

  .row.sell .col.side {
    color: var(--sell, #ef4444);
  }

  .empty {
    padding: 20px;
    text-align: center;
    color: var(--text-muted, #888);
  }
</style>
