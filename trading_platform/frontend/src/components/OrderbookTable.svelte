<script lang="ts">
  export let dom: { ts: number; bids: [number, number][]; asks: [number, number][] } | null = null
  export let depth: number = 20

  $: bids = dom?.bids?.slice(0, depth) || []
  $: asks = dom?.asks?.slice(0, depth) || []

  // Calculate cumulative totals
  $: bidsWithTotal = bids.map((bid, i) => {
    const total = bids.slice(0, i + 1).reduce((sum, [_, size]) => sum + size, 0)
    return { price: bid[0], size: bid[1], total }
  })

  $: asksWithTotal = asks.map((ask, i) => {
    const total = asks.slice(0, i + 1).reduce((sum, [_, size]) => sum + size, 0)
    return { price: ask[0], size: ask[1], total }
  })

  $: maxTotal = Math.max(
    ...bidsWithTotal.map(b => b.total),
    ...asksWithTotal.map(a => a.total),
    1
  )

  function formatPrice(price: number): string {
    return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  function formatSize(size: number): string {
    if (size >= 1000) return size.toFixed(2)
    if (size >= 1) return size.toFixed(4)
    return size.toFixed(6)
  }
</script>

<div class="orderbook">
  <div class="orderbook-header">
    <div class="header-col">Price</div>
    <div class="header-col">Size</div>
    <div class="header-col">Total</div>
  </div>
  <div class="orderbook-body">
    <!-- Asks (top, red) -->
    <div class="asks">
      {#each asksWithTotal as ask}
        <div class="row ask" style="--width: {(ask.total / maxTotal) * 100}%">
          <div class="col price">{formatPrice(ask.price)}</div>
          <div class="col size">{formatSize(ask.size)}</div>
          <div class="col total">{formatSize(ask.total)}</div>
        </div>
      {/each}
    </div>
    <!-- Spread -->
    {#if bids.length > 0 && asks.length > 0}
      <div class="spread">
        <div class="spread-label">Spread</div>
        <div class="spread-value">
          {formatPrice(asks[0][0] - bids[0][0])} ({(asks[0][0] - bids[0][0]) / bids[0][0] * 10000} bps)
        </div>
      </div>
    {/if}
    <!-- Bids (bottom, green) -->
    <div class="bids">
      {#each bidsWithTotal as bid}
        <div class="row bid" style="--width: {(bid.total / maxTotal) * 100}%">
          <div class="col price">{formatPrice(bid.price)}</div>
          <div class="col size">{formatSize(bid.size)}</div>
          <div class="col total">{formatSize(bid.total)}</div>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .orderbook {
    display: flex;
    flex-direction: column;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    color: var(--text, #e0e0e0);
    background: var(--bg-panel, #0a0a0a);
  }

  .orderbook-header {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border, #333);
    font-weight: 600;
    font-size: 11px;
    color: var(--text-muted, #888);
  }

  .orderbook-body {
    display: flex;
    flex-direction: column;
    max-height: 600px;
    overflow-y: auto;
  }

  .asks {
    display: flex;
    flex-direction: column-reverse;
  }

  .bids {
    display: flex;
    flex-direction: column;
  }

  .row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    padding: 2px 8px;
    position: relative;
    cursor: pointer;
    transition: background 0.1s;
  }

  .row:hover {
    background: rgba(255, 255, 255, 0.05);
  }

  .row.ask {
    color: var(--sell, #ef4444);
  }

  .row.ask::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: var(--width);
    background: rgba(239, 68, 68, 0.1);
    z-index: -1;
  }

  .row.bid {
    color: var(--buy, #10b981);
  }

  .row.bid::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: var(--width);
    background: rgba(16, 185, 129, 0.1);
    z-index: -1;
  }

  .col {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .col.price {
    text-align: left;
  }

  .spread {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px;
    border-top: 1px solid var(--border, #333);
    border-bottom: 1px solid var(--border, #333);
    background: var(--bg, #050505);
    font-weight: 600;
  }

  .spread-label {
    font-size: 11px;
    color: var(--text-muted, #888);
  }

  .spread-value {
    font-size: 12px;
    color: var(--text, #e0e0e0);
  }
</style>
