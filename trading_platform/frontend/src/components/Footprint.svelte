<script lang="ts">
  import { formatPrice, formatTime } from '../lib/format'

  interface FootprintLevel {
    price: number
    vol_bid: number
    vol_ask: number
    delta: number
  }
  interface ImbalanceLevel {
    price: number
    side: string
    ratio: number
  }
  interface FootprintBar {
    start: number
    end: number
    levels: FootprintLevel[]
    poc_price?: number | null
    imbalance_levels?: ImbalanceLevel[]
  }

  export let bars: FootprintBar[] = []
  export let maxBars = 10
  export let showDelta = true
  export let sortLevelsBy: 'price' | 'volume' = 'price'
  export let colorBid = 'var(--buy)'
  export let colorAsk = 'var(--sell)'
  export let colorDeltaPos = 'var(--buy)'
  export let colorDeltaNeg = 'var(--sell)'
  let settingsOpen = false
  $: lastBars = bars.slice(-maxBars)
  function barDeltaSum(bar: { levels: Array<{ delta: number }> }): number {
    return bar.levels.reduce((a, l) => a + l.delta, 0)
  }
  function sortedLevels(levels: FootprintLevel[]): FootprintLevel[] {
    if (sortLevelsBy === 'volume') return [...levels].sort((a, b) => (b.vol_bid + b.vol_ask) - (a.vol_bid + a.vol_ask))
    return levels
  }
  function isPoc(bar: FootprintBar, level: FootprintLevel): boolean {
    return bar.poc_price != null && bar.poc_price === level.price
  }
  function getImbalance(bar: FootprintBar, level: FootprintLevel): ImbalanceLevel | undefined {
    return bar.imbalance_levels?.find((im) => im.price === level.price)
  }
</script>

<div class="footprint" style="--fp-bid: {colorBid}; --fp-ask: {colorAsk}; --fp-delta-pos: {colorDeltaPos}; --fp-delta-neg: {colorDeltaNeg};">
  <button type="button" class="footprint-settings-btn" title="Настройки" on:click={() => (settingsOpen = !settingsOpen)}>⚙</button>
  {#if settingsOpen}
    <div class="footprint-settings">
      <label>Баров <input type="number" min="1" max="50" bind:value={maxBars} /></label>
      <label><input type="checkbox" bind:checked={showDelta} /> Delta</label>
      <label>Сортировка <select bind:value={sortLevelsBy}><option value="price">По цене</option><option value="volume">По объёму</option></select></label>
      <label>Bid <input type="color" bind:value={colorBid} /></label>
      <label>Ask <input type="color" bind:value={colorAsk} /></label>
    </div>
  {/if}
  {#each lastBars as bar}
    {@const sumDelta = barDeltaSum(bar)}
    {@const levels = sortedLevels(bar.levels)}
    <div class="bar-block">
      <div class="bar-header">
        <span class="bar-time">{formatTime(bar.start)}</span>
        <span class="bar-meta">
          {#if bar.poc_price != null}
            <span class="poc-badge" title="Point of Control">POC</span>
          {/if}
          {#if showDelta}
            <span class="bar-delta" class:delta-pos={sumDelta >= 0} class:delta-neg={sumDelta < 0}>
              Δ {sumDelta >= 0 ? '+' : ''}{sumDelta.toFixed(0)}
            </span>
          {/if}
        </span>
      </div>
      <div class="level level-head" class:no-delta={!showDelta}>
        <span class="price">Price</span>
        <span class="bid">Bid</span>
        <span class="ask">Ask</span>
        {#if showDelta}<span class="delta">Δ</span>{/if}
      </div>
      <div class="levels">
        {#each levels as level}
          {@const imbalance = getImbalance(bar, level)}
          <div
            class="level"
            class:no-delta={!showDelta}
            class:delta-pos={level.delta >= 0}
            class:delta-neg={level.delta < 0}
            class:poc-level={isPoc(bar, level)}
            class:imbalance-buy={imbalance?.side === 'buy'}
            class:imbalance-sell={imbalance?.side === 'sell'}
          >
            <span class="price">
              {#if isPoc(bar, level)}<span class="poc-dot" title="POC">●</span>{/if}
              {#if imbalance}<span class="imbalance-icon" title="Imbalance {imbalance.side} {imbalance.ratio}×">!</span>{/if}
              {formatPrice(level.price)}
            </span>
            <span class="bid">{level.vol_bid.toFixed(0)}</span>
            <span class="ask">{level.vol_ask.toFixed(0)}</span>
            {#if showDelta}<span class="delta">{level.delta >= 0 ? '+' : ''}{level.delta.toFixed(0)}</span>{/if}
          </div>
        {/each}
      </div>
    </div>
  {/each}
  {#if lastBars.length === 0}
    <div class="empty">No footprint data. Данные появятся после подключения и поступления сделок.</div>
  {/if}
</div>

<style>
  .footprint { padding: 4px; display: flex; gap: 12px; overflow-x: auto; font-size: 11px; }
  .bar-block { flex: 0 0 auto; border: 1px solid var(--border); padding: 4px; background: #050505; }
  .bar-header { display: flex; justify-content: space-between; align-items: center; color: var(--text-muted); margin-bottom: 4px; }
  .bar-time { font-variant-numeric: tabular-nums; }
  .bar-meta { display: flex; align-items: center; gap: 6px; }
  .poc-badge { font-size: 9px; padding: 1px 4px; background: var(--border-strong); color: var(--text-muted); border-radius: 2px; }
  .bar-delta { font-weight: 600; font-variant-numeric: tabular-nums; }
  .level.poc-level { background: rgba(255, 255, 255, 0.06); border-left: 2px solid var(--text-muted); }
  .level.imbalance-buy .price { color: var(--fp-bid); }
  .level.imbalance-sell .price { color: var(--fp-ask); }
  .poc-dot { color: var(--text-muted); margin-right: 4px; font-size: 8px; }
  .imbalance-icon { color: #f59e0b; margin-right: 4px; font-weight: 700; font-size: 10px; }
  .bar-delta.delta-pos { color: var(--buy); }
  .bar-delta.delta-neg { color: var(--sell); }
  .level-head { color: var(--text-muted); font-size: 10px; margin-bottom: 2px; }
  .levels { display: flex; flex-direction: column; gap: 2px; }
  .level { display: grid; grid-template-columns: 60px 40px 40px 40px; gap: 8px; align-items: center; }
  .level.no-delta, .level-head.no-delta { grid-template-columns: 60px 40px 40px; }
  .level.delta-pos .delta { color: var(--fp-delta-pos, var(--buy)); }
  .level.delta-neg .delta { color: var(--fp-delta-neg, var(--sell)); }
  .bid { color: var(--fp-bid); }
  .ask { color: var(--fp-ask); }
  .empty { color: var(--text-muted); padding: 8px; }
  .footprint { position: relative; }
  .footprint-settings-btn { position: absolute; top: 4px; right: 4px; padding: 2px 6px; font-size: 12px; background: #111; border: 1px solid var(--border); color: var(--text); cursor: pointer; z-index: 5; }
  .footprint-settings { position: absolute; top: 28px; right: 4px; background: var(--bg-panel); border: 1px solid var(--border-strong); padding: 8px; z-index: 20; display: flex; flex-direction: column; gap: 4px; font-size: 11px; }
  .footprint-settings label { display: flex; align-items: center; gap: 6px; }
  .footprint-settings input[type="number"] { width: 48px; }
</style>
