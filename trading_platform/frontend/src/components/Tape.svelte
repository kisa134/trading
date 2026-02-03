<script lang="ts">
  export let trades: Array<{ side: string; price: number; size: number; ts: number }> = []
  const max = 80
  $: list = trades.slice(0, max)
</script>

<div class="tape">
  {#each list as t}
    <div class="row" class:buy={(t.side || '').toLowerCase().startsWith('b')} class:sell={!(t.side || '').toLowerCase().startsWith('b')}>
      <span class="price">{t.price.toFixed(2)}</span>
      <span class="size">{t.size.toFixed(2)}</span>
    </div>
  {/each}
  {#if list.length === 0}
    <div class="empty">No trades</div>
  {/if}
</div>

<style>
  .tape { padding: 4px; max-height: 200px; overflow-y: auto; font-size: 11px; }
  .row { display: flex; justify-content: space-between; padding: 2px 4px; }
  .row.buy { color: var(--buy); }
  .row.sell { color: var(--sell); }
  .price { font-variant-numeric: tabular-nums; }
  .size { color: var(--text-muted); }
  .empty { color: var(--text-muted); padding: 8px; }
</style>
