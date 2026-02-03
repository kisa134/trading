<script lang="ts">
  import { formatPrice, formatTime } from '../lib/format'
  export let bars: Array<{ start: number; end: number; levels: Array<{ price: number; vol_bid: number; vol_ask: number; delta: number }> }> = []
  const maxBars = 10
  $: lastBars = bars.slice(-maxBars)
  function barDeltaSum(bar: { levels: Array<{ delta: number }> }): number {
    return bar.levels.reduce((a, l) => a + l.delta, 0)
  }
</script>

<div class="footprint">
  {#each lastBars as bar}
    <div class="bar-block">
      <div class="bar-header">
        <span class="bar-time">{formatTime(bar.start)}</span>
        {@const sumDelta = barDeltaSum(bar)}
        <span class="bar-delta" class:delta-pos={sumDelta >= 0} class:delta-neg={sumDelta < 0}>
          Δ {sumDelta >= 0 ? '+' : ''}{sumDelta.toFixed(0)}
        </span>
      </div>
      <div class="level level-head">
        <span class="price">Price</span>
        <span class="bid">Bid</span>
        <span class="ask">Ask</span>
        <span class="delta">Δ</span>
      </div>
      <div class="levels">
        {#each bar.levels as level}
          <div class="level" class:delta-pos={level.delta >= 0} class:delta-neg={level.delta < 0}>
            <span class="price">{formatPrice(level.price)}</span>
            <span class="bid">{level.vol_bid.toFixed(0)}</span>
            <span class="ask">{level.vol_ask.toFixed(0)}</span>
            <span class="delta">{level.delta >= 0 ? '+' : ''}{level.delta.toFixed(0)}</span>
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
  .bar-delta { font-weight: 600; font-variant-numeric: tabular-nums; }
  .bar-delta.delta-pos { color: var(--buy); }
  .bar-delta.delta-neg { color: var(--sell); }
  .level-head { color: var(--text-muted); font-size: 10px; margin-bottom: 2px; }
  .levels { display: flex; flex-direction: column; gap: 2px; }
  .level { display: grid; grid-template-columns: 60px 40px 40px 40px; gap: 8px; align-items: center; }
  .level.delta-pos .delta { color: var(--buy); }
  .level.delta-neg .delta { color: var(--sell); }
  .bid { color: var(--buy); }
  .ask { color: var(--sell); }
  .empty { color: var(--text-muted); padding: 8px; }
</style>
