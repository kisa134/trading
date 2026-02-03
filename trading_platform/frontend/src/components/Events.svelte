<script lang="ts">
  export let items: Array<{ type: string; ts: number; [k: string]: unknown }> = []
  $: list = items.slice(0, 30)
  function typeClass(t: string) {
    if (t.includes('ICEBERG')) return 'iceberg'
    if (t.includes('WALL')) return 'wall'
    if (t.includes('SPOOF')) return 'spoof'
    return ''
  }
</script>

<div class="events">
  {#each list as ev}
    <div class="event {typeClass(ev.type)}">
      <span class="type">{ev.type}</span>
      {#if ev.price != null}<span class="price">{Number(ev.price).toFixed(2)}</span>{/if}
      {#if ev.side}<span class="side">{ev.side}</span>{/if}
    </div>
  {/each}
  {#if list.length === 0}
    <div class="empty">No events</div>
  {/if}
</div>

<style>
  .events { padding: 4px; max-height: 180px; overflow-y: auto; font-size: 11px; }
  .event { padding: 4px; border-left: 3px solid #333; margin-bottom: 2px; background: #050505; }
  .event.iceberg { border-left-color: var(--buy); }
  .event.wall { border-left-color: #f59e0b; }
  .event.spoof { border-left-color: var(--sell); }
  .type { color: var(--text-muted); margin-right: 6px; }
  .price { font-variant-numeric: tabular-nums; margin-right: 4px; }
  .side { color: var(--text-muted); }
  .empty { color: var(--text-muted); padding: 8px; }
</style>
