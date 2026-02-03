<script lang="ts">
  import { formatPrice, formatRelativeTime } from '../lib/format'
  export let items: Array<{ type: string; ts: number; [k: string]: unknown }> = []
  export let maxItems = 30
  let selectedEvent: { type: string; ts: number; [k: string]: unknown } | null = null
  $: list = items.slice(0, maxItems)
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
  function formatDetailValue(v: unknown): string {
    if (v == null) return '—'
    if (typeof v === 'number') return String(v)
    if (typeof v === 'string') return v
    if (Array.isArray(v)) return JSON.stringify(v)
    return JSON.stringify(v)
  }
</script>

<div class="events">
  {#each list as ev}
    <button type="button" class="event {typeClass(ev.type)}" on:click={() => (selectedEvent = ev)}>
      <span class="type">{typeLabel(ev.type)}</span>
      {#if ev.price != null}<span class="price">{formatPrice(Number(ev.price))}</span>{/if}
      {#if ev.side}<span class="side">{ev.side}</span>{/if}
      <span class="time">{formatRelativeTime(ev.ts)}</span>
    </button>
  {/each}
  {#if list.length === 0}
    <div class="empty">No events. Данные появятся после подключения и поступления событий.</div>
  {/if}
</div>
{#if selectedEvent}
  <div class="event-modal-backdrop" role="dialog" aria-modal="true" on:click={() => (selectedEvent = null)} on:keydown={(e) => e.key === 'Escape' && (selectedEvent = null)}>
    <div class="event-modal" on:click|stopPropagation>
      <div class="event-modal-header">
        <h3>{typeLabel(selectedEvent.type)}</h3>
        <button type="button" class="close-btn" on:click={() => (selectedEvent = null)}>×</button>
      </div>
      <dl class="event-detail-list">
        {#each Object.entries(selectedEvent) as [key, value]}
          <dt>{key}</dt>
          <dd>{key === 'price' && typeof value === 'number' ? formatPrice(value) : key === 'ts' ? formatRelativeTime(Number(value)) + ' (' + new Date(Number(value) < 10_000_000_000 ? Number(value) * 1000 : Number(value)).toISOString() + ')' : formatDetailValue(value)}</dd>
        {/each}
      </dl>
    </div>
  </div>
{/if}

<style>
  .events { padding: 4px; max-height: 180px; overflow-y: auto; font-size: 11px; }
  .event { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 4px; border-left: 3px solid #333; margin-bottom: 2px; background: #050505; width: 100%; text-align: left; cursor: pointer; border-right: none; border-top: none; border-bottom: none; color: inherit; font: inherit; }
  .event:hover { background: #0a0a0a; }
  .event.iceberg { border-left-color: var(--buy); }
  .event.wall { border-left-color: #f59e0b; }
  .event.spoof { border-left-color: var(--sell); }
  .type { color: var(--text); font-weight: 500; }
  .price { font-variant-numeric: tabular-nums; }
  .side { color: var(--text-muted); }
  .time { font-size: 10px; color: var(--text-muted); margin-left: auto; }
  .empty { color: var(--text-muted); padding: 8px; }
  .event-modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 16px; }
  .event-modal { background: var(--bg-panel); border: 1px solid var(--border-strong); max-width: 400px; width: 100%; max-height: 80vh; overflow: auto; }
  .event-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border); }
  .event-modal-header h3 { margin: 0; font-size: 14px; }
  .close-btn { padding: 2px 8px; background: transparent; border: 1px solid var(--border); color: var(--text); cursor: pointer; font-size: 18px; line-height: 1; }
  .event-detail-list { padding: 12px; margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 4px 16px; font-size: 12px; }
  .event-detail-list dt { color: var(--text-muted); }
  .event-detail-list dd { margin: 0; word-break: break-all; }
</style>
