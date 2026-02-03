<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte'
  import { GridStack } from 'gridstack'
  import 'gridstack/dist/gridstack.min.css'
  import Dom from './Dom.svelte'
  import Tape from './Tape.svelte'
  import Heatmap from './Heatmap.svelte'
  import Footprint from './Footprint.svelte'
  import Events from './Events.svelte'
  import Chart from './Chart.svelte'
  import TrendAI from './TrendAI.svelte'

  export let symbol = 'BTCUSDT'
  export let dom: { ts: number; bids: [number, number][]; asks: [number, number][] } | null = null
  export let trades: Array<{ side: string; price: number; size: number; ts: number }> = []
  export let heatmapSlices: Array<{ ts: number; rows: Array<{ price: number; vol_bid: number; vol_ask: number }> }> = []
  export let footprintBars: Array<{ start: number; end: number; levels: Array<{ price: number; vol_bid: number; vol_ask: number; delta: number }> }> = []
  export let events: Array<{ type: string; ts: number; [k: string]: unknown }> = [] // viewEvents from parent
  export let candles: Array<{ start: number; open: number; high: number; low: number; close: number; volume: number }> = []
  export let windowStart = 0
  export let windowEnd = 0
  export let setTimeWindow: (start: number, end: number) => void = () => {}
  export let trendScores: Array<{ ts: number; trend_power: number; trend_power_delta: number }> = []
  export let exhaustionScores: Array<{ ts: number; exhaustion_score: number; absorption_score: number }> = []
  export let ruleSignals: Array<{ ts: number; prob_reversal_rule: number; reversal_horizon_bars: number; expected_move_range: [number, number] }> = []

  const LAYOUT_KEY = 'trading-dashboard-layout'
  type WidgetType = 'dom' | 'heatmap' | 'tape' | 'events' | 'footprint' | 'chart' | 'trendai' | 'mllab'
  type Widget = { id: string; type: WidgetType; x: number; y: number; w: number; h: number }
  const defaultWidgets: Widget[] = [
    { id: 'w1', type: 'dom', x: 0, y: 0, w: 3, h: 4 },
    { id: 'w2', type: 'chart', x: 3, y: 0, w: 6, h: 2 },
    { id: 'w3', type: 'heatmap', x: 3, y: 2, w: 6, h: 4 },
    { id: 'w4', type: 'tape', x: 9, y: 0, w: 3, h: 3 },
    { id: 'w5', type: 'events', x: 9, y: 3, w: 3, h: 3 },
    { id: 'w6', type: 'footprint', x: 0, y: 4, w: 12, h: 2 },
  ]

  let widgets: Widget[] = []
  let gridEl: HTMLDivElement
  let grid: ReturnType<typeof GridStack.init> | null = null
  let addWidgetType: WidgetType = 'heatmap'

  function loadLayout(): Widget[] {
    try {
      const raw = localStorage.getItem(LAYOUT_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length > 0) return parsed
      }
    } catch (_) {}
    return defaultWidgets.map((w) => ({ ...w }))
  }

  function saveLayout() {
    try {
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(widgets))
    } catch (_) {}
  }

  const inWindow = (ts: number) => {
    const t = ts < 10_000_000_000 ? ts * 1000 : ts
    return t >= windowStart && t <= windowEnd
  }
  $: viewHeatmap = heatmapSlices.filter((s) => inWindow(s.ts))
  $: viewFootprint = footprintBars.filter((b) => inWindow(b.start))

  async function addWidget() {
    const id = 'w' + Date.now()
    const y = widgets.length > 0 ? Math.max(...widgets.map((w) => w.y + w.h)) + 1 : 0
    widgets = [...widgets, { id, type: addWidgetType, x: 0, y, w: 4, h: 2 }]
    saveLayout()
    await tick()
    if (grid) {
      const el = gridEl.querySelector(`[data-gs-id="${id}"]`) as HTMLElement
      if (el) grid.makeWidget(el)
    }
  }

  function removeWidget(id: string) {
    widgets = widgets.filter((w) => w.id !== id)
    saveLayout()
    const item = gridEl.querySelector(`[data-gs-id="${id}"]`) as HTMLElement
    if (item && grid) grid.removeWidget(item, false)
  }

  onMount(() => {
    widgets = loadLayout()
    grid = GridStack.init(
      { column: 12, cellHeight: 80, margin: 8, float: true },
      gridEl
    )
    grid.on('change', () => {
      const items = grid?.getGridItems() ?? []
      widgets = widgets.map((w) => {
        const el = items.find((i: HTMLElement) => i.getAttribute('data-gs-id') === w.id)
        if (!el) return w
        const x = parseInt(el.getAttribute('data-gs-x') ?? '0', 10)
        const y = parseInt(el.getAttribute('data-gs-y') ?? '0', 10)
        const ww = parseInt(el.getAttribute('data-gs-w') ?? '2', 10)
        const h = parseInt(el.getAttribute('data-gs-h') ?? '2', 10)
        return { ...w, x, y, w: ww, h }
      })
      saveLayout()
    })
  })

  onDestroy(() => {
    grid?.destroy(false)
    grid = null
  })
</script>

<div class="dashboard">
  <div class="dashboard-toolbar">
    <span>Добавить виджет:</span>
    <select bind:value={addWidgetType}>
      <option value="dom">DOM</option>
      <option value="chart">Chart</option>
      <option value="heatmap">Heatmap</option>
      <option value="tape">Tape</option>
      <option value="events">Events</option>
      <option value="footprint">Footprint</option>
      <option value="trendai">Trend AI</option>
      <option value="mllab">ML Lab</option>
    </select>
    <button type="button" on:click={addWidget}>+</button>
  </div>
  <div class="grid-stack" bind:this={gridEl}>
    {#each widgets as w}
      <div
        class="grid-stack-item"
        data-gs-id={w.id}
        data-gs-x={w.x}
        data-gs-y={w.y}
        data-gs-w={w.w}
        data-gs-h={w.h}
      >
        <div class="grid-stack-item-content panel widget-panel">
          <div class="panel-title widget-title">
            <span>{w.type} · {symbol}</span>
            <button type="button" class="remove-widget" on:click={() => removeWidget(w.id)} title="Удалить">×</button>
          </div>
          <div class="widget-body">
            {#if w.type === 'dom'}
              <Dom data={dom} depth={20} />
            {:else if w.type === 'chart'}
              <Chart candles={candles} windowStart={windowStart} windowEnd={windowEnd} onTimeWindowChange={setTimeWindow} />
            {:else if w.type === 'heatmap'}
              <Heatmap slices={viewHeatmap} windowStart={windowStart} windowEnd={windowEnd} onTimeWindowChange={setTimeWindow} />
            {:else if w.type === 'tape'}
              <Tape trades={trades} />
            {:else if w.type === 'events'}
              <Events items={events} />
            {:else if w.type === 'footprint'}
              <Footprint bars={viewFootprint} />
            {:else if w.type === 'trendai'}
              <TrendAI trendScores={trendScores} exhaustionScores={exhaustionScores} ruleSignals={ruleSignals} />
            {:else if w.type === 'mllab'}
              <div class="mllab-placeholder">ML Lab: Mamba и метрики будут добавлены в v2.</div>
            {/if}
          </div>
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  .dashboard { padding: 8px; height: 100%; display: flex; flex-direction: column; min-height: 0; }
  .dashboard-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .dashboard-toolbar select { padding: 4px 8px; background: #020202; border: 1px solid var(--border-strong); color: var(--text); }
  .grid-stack { flex: 1; min-height: 300px; }
  .widget-panel { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
  .widget-title { display: flex; justify-content: space-between; align-items: center; }
  .remove-widget { padding: 2px 6px; background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; }
  .remove-widget:hover { color: var(--sell); }
  .widget-body { flex: 1; overflow: auto; min-height: 0; }
  .mllab-placeholder { padding: 12px; color: var(--text-muted); }
  :global(.grid-stack-item-content) { overflow: auto !important; }
</style>
