<script lang="ts">
  import { formatPrice, formatSize, formatRelativeTime } from '../lib/format'
  export let trades: Array<{ side: string; price: number; size: number; ts: number }> = []
  export let maxRows = 500
  export let showTime = true
  export let showSize = true
  export let sortNewestFirst = true
  export let colorBuy = 'var(--buy)'
  export let colorSell = 'var(--sell)'

  const ROW_HEIGHT = 24
  let scrollEl: HTMLDivElement
  let scrollTop = 0
  let viewportHeight = 180

  $: list = (sortNewestFirst ? trades : [...trades].reverse()).slice(0, maxRows)
  $: volBuy = list.filter(t => (t.side || '').toLowerCase().startsWith('b')).reduce((a, t) => a + t.size, 0)
  $: volSell = list.filter(t => !(t.side || '').toLowerCase().startsWith('b')).reduce((a, t) => a + t.size, 0)

  $: totalHeight = list.length * ROW_HEIGHT
  $: visibleStart = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT))
  $: visibleCount = Math.ceil(viewportHeight / ROW_HEIGHT) + 2
  $: visibleEnd = Math.min(list.length, visibleStart + visibleCount)
  $: visibleList = list.slice(visibleStart, visibleEnd)
  $: offsetY = visibleStart * ROW_HEIGHT

  function handleScroll() {
    if (scrollEl) {
      scrollTop = scrollEl.scrollTop
      viewportHeight = scrollEl.clientHeight
    }
  }
</script>

<div class="tape">
  {#if list.length > 0}
    <div class="vol-summary">Buy: {formatSize(volBuy)} | Sell: {formatSize(volSell)}</div>
    <div
      class="tape-viewport"
      bind:this={scrollEl}
      on:scroll={handleScroll}
      role="list"
      aria-label="Trade tape"
    >
      <div class="tape-spacer" style="height: {totalHeight}px">
        <div class="tape-visible" style="transform: translateY({offsetY}px)">
          {#each visibleList as t}
            {@const isBuy = (t.side || '').toLowerCase().startsWith('b')}
            <div class="row" class:buy={isBuy} class:sell={!isBuy} style="--tape-buy: {colorBuy}; --tape-sell: {colorSell};">
              {#if showTime}<span class="time" title={new Date(t.ts < 10_000_000_000 ? t.ts * 1000 : t.ts).toISOString()}>{formatRelativeTime(t.ts)}</span>{/if}
              <span class="price">{formatPrice(t.price)}</span>
              {#if showSize}<span class="size">{formatSize(t.size)}</span>{/if}
            </div>
          {/each}
        </div>
      </div>
    </div>
  {:else}
    <div class="empty">No trades. Данные появятся после подключения и поступления сделок.</div>
  {/if}
</div>

<style>
  .tape { padding: 4px; font-size: 11px; display: flex; flex-direction: column; max-height: 200px; }
  .vol-summary { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; padding: 2px 4px; flex-shrink: 0; }
  .tape-viewport { overflow-y: auto; overflow-x: hidden; flex: 1; min-height: 0; }
  .tape-spacer { position: relative; }
  .tape-visible { position: absolute; left: 0; right: 0; top: 0; }
  .row { display: grid; grid-template-columns: 48px 1fr auto; gap: 8px; align-items: center; padding: 2px 4px; height: 24px; box-sizing: border-box; }
  .row.buy { color: var(--tape-buy, var(--buy)); border-left: 2px solid var(--tape-buy, var(--buy)); }
  .row.sell { color: var(--tape-sell, var(--sell)); border-left: 2px solid var(--tape-sell, var(--sell)); }
  .time { font-size: 10px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .price { font-variant-numeric: tabular-nums; }
  .size { color: var(--text-muted); }
  .empty { color: var(--text-muted); padding: 8px; }
</style>
