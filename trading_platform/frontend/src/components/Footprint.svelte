<script lang="ts">
  export let bars: Array<{ start: number; end: number; levels: Array<{ price: number; vol_bid: number; vol_ask: number; delta: number }> }> = []
  $: lastBars = bars.slice(-3)
</script>

<div class="footprint">
  {#each lastBars as bar}
    <div class="bar-block">
      <div class="bar-header">{new Date(bar.start).toLocaleTimeString()}</div>
      <div class="levels">
        {#each bar.levels as level}
          <div class="level" class:delta-pos={level.delta >= 0} class:delta-neg={level.delta < 0}>
            <span class="price">{level.price.toFixed(2)}</span>
            <span class="bid">{level.vol_bid.toFixed(0)}</span>
            <span class="ask">{level.vol_ask.toFixed(0)}</span>
            <span class="delta">{level.delta >= 0 ? '+' : ''}{level.delta.toFixed(0)}</span>
          </div>
        {/each}
      </div>
    </div>
  {/each}
  {#if lastBars.length === 0}
    <div class="empty">No footprint data</div>
  {/if}
</div>

<style>
  .footprint { padding: 4px; display: flex; gap: 12px; overflow-x: auto; font-size: 11px; }
  .bar-block { flex: 0 0 auto; border: 1px solid var(--border); padding: 4px; background: #050505; }
  .bar-header { color: var(--text-muted); margin-bottom: 4px; }
  .levels { display: flex; flex-direction: column; gap: 2px; }
  .level { display: grid; grid-template-columns: 60px 40px 40px 40px; gap: 8px; }
  .level.delta-pos .delta { color: var(--buy); }
  .level.delta-neg .delta { color: var(--sell); }
  .bid { color: var(--buy); }
  .ask { color: var(--sell); }
  .empty { color: var(--text-muted); padding: 8px; }
</style>
