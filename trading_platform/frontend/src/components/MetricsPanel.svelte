<script lang="ts">
  import { formatPrice, formatTime } from '../lib/format'

  export let lastPrice: number | null = null
  export let openInterest: Array<{ ts: number; open_interest: number; open_interest_value?: number }> = []
  export let liquidations: Array<{ ts: number; price: number; quantity: number; side: string }> = []
  export let maxLiquidations: number = 10

  $: currentOI = openInterest.length > 0 ? openInterest[openInterest.length - 1] : null
  $: oiChange = openInterest.length >= 2
    ? openInterest[openInterest.length - 1].open_interest - openInterest[openInterest.length - 2].open_interest
    : 0
  $: recentLiquidations = liquidations.slice(0, maxLiquidations)
</script>

<div class="metrics">
  <div class="metric-section">
    <div class="section-title">Last Price</div>
    <div class="price-value">{lastPrice != null ? formatPrice(lastPrice) : '—'}</div>
  </div>

  <div class="metric-section">
    <div class="section-title">Open Interest</div>
    {#if currentOI}
      <div class="oi-value">{formatPrice(currentOI.open_interest, 0)}</div>
      <div class="oi-change" class:positive={oiChange > 0} class:negative={oiChange < 0}>
        {oiChange > 0 ? '+' : ''}{formatPrice(oiChange, 0)}
      </div>
      {#if currentOI.open_interest_value != null}
        <div class="oi-value-usd">${formatPrice(currentOI.open_interest_value, 0)}</div>
      {/if}
    {:else}
      <div class="empty">—</div>
    {/if}
  </div>

  <div class="metric-section">
    <div class="section-title">Liquidations</div>
    <div class="liquidations-list">
      {#each recentLiquidations as liq}
        <div class="liq-item" class:buy={(liq.side || '').toLowerCase() === 'buy'} class:sell={(liq.side || '').toLowerCase() === 'sell'}>
          <div class="liq-price">{formatPrice(liq.price)}</div>
          <div class="liq-qty">{formatPrice(liq.quantity, 2)}</div>
          <div class="liq-side">{liq.side}</div>
          <div class="liq-time">{formatTime(liq.ts)}</div>
        </div>
      {/each}
      {#if recentLiquidations.length === 0}
        <div class="empty">No liquidations</div>
      {/if}
    </div>
  </div>
</div>

<style>
  .metrics {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 12px;
    background: var(--bg-panel, #0a0a0a);
    font-family: 'Courier New', monospace;
    font-size: 12px;
  }

  .metric-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .section-title {
    font-size: 11px;
    color: var(--text-muted, #888);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .price-value {
    font-size: 24px;
    font-weight: 700;
    color: var(--text, #e0e0e0);
    font-variant-numeric: tabular-nums;
  }

  .oi-value {
    font-size: 18px;
    font-weight: 600;
    color: var(--text, #e0e0e0);
    font-variant-numeric: tabular-nums;
  }

  .oi-change {
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .oi-change.positive {
    color: var(--buy, #10b981);
  }

  .oi-change.negative {
    color: var(--sell, #ef4444);
  }

  .oi-value-usd {
    font-size: 11px;
    color: var(--text-muted, #888);
    font-variant-numeric: tabular-nums;
  }

  .liquidations-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 200px;
    overflow-y: auto;
  }

  .liq-item {
    display: grid;
    grid-template-columns: 1fr 1fr 0.8fr 1fr;
    gap: 8px;
    padding: 4px 6px;
    border-left: 2px solid transparent;
    font-size: 10px;
    background: rgba(255, 255, 255, 0.02);
  }

  .liq-item.buy {
    border-left-color: var(--buy, #10b981);
  }

  .liq-item.sell {
    border-left-color: var(--sell, #ef4444);
  }

  .liq-price {
    font-variant-numeric: tabular-nums;
    color: var(--text, #e0e0e0);
  }

  .liq-qty {
    font-variant-numeric: tabular-nums;
    color: var(--text, #e0e0e0);
  }

  .liq-side {
    font-weight: 600;
  }

  .liq-item.buy .liq-side {
    color: var(--buy, #10b981);
  }

  .liq-item.sell .liq-side {
    color: var(--sell, #ef4444);
  }

  .liq-time {
    font-size: 9px;
    color: var(--text-muted, #888);
    font-variant-numeric: tabular-nums;
  }

  .empty {
    color: var(--text-muted, #888);
    font-style: italic;
    padding: 8px 0;
  }
</style>
