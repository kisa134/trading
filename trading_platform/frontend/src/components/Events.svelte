<script lang="ts">
  import { formatPrice, formatRelativeTime } from '../lib/format'
  export let items: Array<{ type: string; ts: number; [k: string]: unknown }> = []
  $: list = items.slice(0, 30)
  function typeClass(t: string) {
    if (t.includes('ICEBERG')) return 'iceberg'
    if (t.includes('WALL')) return 'wall'
    if (t.includes('SPOOF')) return 'spoof'
    return ''
  }
  function typeLabel(t: string): string {
    if (t.includes('ICEBERG')) return 'Iceberg'
    if (t.includes('WALL')) return 'Wall'
    if (t.includes('SPOOF')) return 'Spoof'
    return t
  }
</script>

<div class="events">
  {#each list as ev}
    <div class="event {typeClass(ev.type)}">
      <span class="type">{typeLabel(ev.type)}</span>
      {#if ev.price != null}<span class="price">{formatPrice(Number(ev.price))}</span>{/if}
      {#if ev.side}<span class="side">{ev.side}</span>{/if}
      <span class="time">{formatRelativeTime(ev.ts)}</span>
    </div>
  {/each}
  {#if list.length === 0}
    <div class="empty">No events. Данные появятся после подключения и поступления событий.</div>
  {/if}
</div>

<style>
  .events { padding: 4px; max-height: 180px; overflow-y: auto; font-size: 11px; }
  .event { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 4px; border-left: 3px solid #333; margin-bottom: 2px; background: #050505; }
  .event.iceberg { border-left-color: var(--buy); }
  .event.wall { border-left-color: #f59e0b; }
  .event.spoof { border-left-color: var(--sell); }
  .type { color: var(--text); font-weight: 500; }
  .price { font-variant-numeric: tabular-nums; }
  .side { color: var(--text-muted); }
  .time { font-size: 10px; color: var(--text-muted); margin-left: auto; }
  .empty { color: var(--text-muted); padding: 8px; }
</style>
