<script lang="ts">
  import { onMount } from 'svelte'
  export let trendScores: Array<{ ts: number; trend_power: number; trend_power_delta: number }> = []
  export let exhaustionScores: Array<{ ts: number; exhaustion_score: number; absorption_score: number }> = []
  export let ruleSignals: Array<{ ts: number; prob_reversal_rule: number; reversal_horizon_bars: number; expected_move_range: [number, number] }> = []

  let canvasTrend: HTMLCanvasElement
  let canvasExh: HTMLCanvasElement
  let ctxTrend: CanvasRenderingContext2D | null = null
  let ctxExh: CanvasRenderingContext2D | null = null
  let settingsOpen = false
  let signalsExpanded = false
  let minProbFilterPct = 0

  export let maxPoints = 120
  export let showTrendPower = true
  export let showTrendDelta = true
  export let showExhaustion = true
  export let showAbsorption = true
  export let colorTrendPower = '#0d9488'
  export let colorTrendDelta = '#a855f7'
  export let colorExhaustion = '#f59e0b'
  export let colorAbsorption = '#ef4444'

  const paddingLeft = 44
  const paddingBottom = 18
  const paddingRight = 8
  const paddingTop = 8

  $: trend = trendScores.slice(-maxPoints)
  $: exh = exhaustionScores.slice(-maxPoints)
  $: lastSignal = ruleSignals[ruleSignals.length - 1]
  $: latestTrend = trend[trend.length - 1]
  $: latestExh = exh[exh.length - 1]
  $: filteredSignals = ruleSignals.filter((s) => s.prob_reversal_rule >= minProbFilterPct / 100).slice(-20).reverse()

  $: trendPowerVals = trend.map((t) => t.trend_power)
  $: trendDeltaVals = trend.map((t) => t.trend_power_delta)
  $: exhVals = exh.map((e) => e.exhaustion_score)
  $: absVals = exh.map((e) => e.absorption_score)

  function drawChart(
    ctx: CanvasRenderingContext2D,
    series: { values: number[]; color: string }[],
    tsValues: number[]
  ) {
    const w = ctx.canvas.width
    const h = ctx.canvas.height
    const plotW = w - paddingLeft - paddingRight
    const plotH = h - paddingTop - paddingBottom
    ctx.fillStyle = '#050505'
    ctx.fillRect(0, 0, w, h)
    const allVals = series.flatMap(s => s.values).filter(Number.isFinite)
    const min = allVals.length ? Math.min(...allVals) : 0
    const max = allVals.length ? Math.max(...allVals) : 1
    const range = max - min || 1
    ctx.strokeStyle = '#333'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(paddingLeft, paddingTop)
    ctx.lineTo(paddingLeft, h - paddingBottom)
    ctx.lineTo(w - paddingRight, h - paddingBottom)
    ctx.stroke()
    ctx.fillStyle = '#8b8b8b'
    ctx.font = '10px "JetBrains Mono", monospace'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(max.toFixed(1), paddingLeft - 4, paddingTop + 6)
    ctx.fillText(min.toFixed(1), paddingLeft - 4, h - paddingBottom - 6)
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    if (tsValues.length >= 2) {
      ctx.fillText('older', paddingLeft + plotW / 4, h - paddingBottom + 2)
      ctx.fillText('newer', paddingLeft + (3 * plotW) / 4, h - paddingBottom + 2)
    }
    const n = Math.max(...series.map(s => s.values.length), 1)
    series.forEach(({ values, color }) => {
      if (!values.length) return
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.beginPath()
      values.forEach((v, i) => {
        const x = paddingLeft + (i / (n - 1 || 1)) * plotW
        const y = h - paddingBottom - ((v - min) / range) * plotH
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()
    })
  }

  function redraw() {
    const trendSeries: { values: number[]; color: string }[] = []
    if (showTrendPower) trendSeries.push({ values: trendPowerVals, color: colorTrendPower })
    if (showTrendDelta) trendSeries.push({ values: trendDeltaVals, color: colorTrendDelta })
    if (ctxTrend && trendSeries.length) {
      drawChart(ctxTrend, trendSeries, trend.map((t) => t.ts))
    } else if (ctxTrend) {
      ctxTrend.fillStyle = '#050505'
      ctxTrend.fillRect(0, 0, ctxTrend.canvas.width, ctxTrend.canvas.height)
    }
    const exhSeries: { values: number[]; color: string }[] = []
    if (showExhaustion) exhSeries.push({ values: exhVals, color: colorExhaustion })
    if (showAbsorption) exhSeries.push({ values: absVals, color: colorAbsorption })
    if (ctxExh && exhSeries.length) {
      drawChart(ctxExh, exhSeries, exh.map((e) => e.ts))
    } else if (ctxExh) {
      ctxExh.fillStyle = '#050505'
      ctxExh.fillRect(0, 0, ctxExh.canvas.width, ctxExh.canvas.height)
    }
  }

  onMount(() => {
    ctxTrend = canvasTrend?.getContext('2d') ?? null
    ctxExh = canvasExh?.getContext('2d') ?? null
    redraw()
  })

  $: if (trend.length || exh.length) redraw()
</script>

<div class="trend-ai">
  <button type="button" class="trend-settings-btn" title="Настройки" on:click={() => (settingsOpen = !settingsOpen)}>⚙</button>
  {#if settingsOpen}
    <div class="trend-settings">
      <label>Точек <input type="number" min="20" max="500" bind:value={maxPoints} /></label>
      <label><input type="checkbox" bind:checked={showTrendPower} /> TrendPower</label>
      <label><input type="checkbox" bind:checked={showTrendDelta} /> ΔTrendPower</label>
      <label><input type="checkbox" bind:checked={showExhaustion} /> Exhaustion</label>
      <label><input type="checkbox" bind:checked={showAbsorption} /> Absorption</label>
      <label>TrendPower <input type="color" bind:value={colorTrendPower} /></label>
      <label>ΔTrend <input type="color" bind:value={colorTrendDelta} /></label>
      <label>Exh <input type="color" bind:value={colorExhaustion} /></label>
      <label>Abs <input type="color" bind:value={colorAbsorption} /></label>
    </div>
  {/if}
  <div class="charts">
    <div class="panel">
      <div class="panel-title">TrendPower / ΔTrendPower</div>
      <canvas bind:this={canvasTrend} width={800} height={160} style="width: 100%; height: 160px;"></canvas>
      <div class="legend">
        {#if showTrendPower}<span class="leg" style="color: {colorTrendPower}">— TrendPower</span>{/if}
        {#if showTrendDelta}<span class="leg" style="color: {colorTrendDelta}">— ΔTrendPower</span>{/if}
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">Exhaustion / Absorption</div>
      <canvas bind:this={canvasExh} width={800} height={120} style="width: 100%; height: 120px;"></canvas>
      <div class="legend">
        {#if showExhaustion}<span class="leg" style="color: {colorExhaustion}">— Exhaustion</span>{/if}
        {#if showAbsorption}<span class="leg" style="color: {colorAbsorption}">— Absorption</span>{/if}
      </div>
    </div>
  </div>

  <aside class="panel ai-panel">
    <div class="panel-title">AI Trend Engine</div>
    <div class="row" class:up={latestTrend != null && latestTrend.trend_power_delta > 0} class:down={latestTrend != null && latestTrend.trend_power_delta < 0}>
      <span>TrendPower</span>
      <span>{latestTrend ? latestTrend.trend_power.toFixed(1) : '--'}</span>
    </div>
    <div class="row" class:up={latestTrend != null && latestTrend.trend_power_delta > 0} class:down={latestTrend != null && latestTrend.trend_power_delta < 0}>
      <span>ΔTrendPower</span>
      <span>{latestTrend ? latestTrend.trend_power_delta.toFixed(1) : '--'}</span>
    </div>
    <div class="row">
      <span>Exhaustion</span>
      <span>{latestExh ? latestExh.exhaustion_score.toFixed(0) : '--'}</span>
    </div>
    <div class="row">
      <span>Absorption</span>
      <span>{latestExh ? latestExh.absorption_score.toFixed(0) : '--'}</span>
    </div>
    <div class="signals-block">
      <button type="button" class="signals-toggle" on:click={() => (signalsExpanded = !signalsExpanded)}>
        Rule reversal {lastSignal ? Math.round(lastSignal.prob_reversal_rule * 100) + '%' : '--'}
      </button>
      {#if signalsExpanded}
        <div class="signals-filter">
          <label>Мин. вероятность <input type="range" min="0" max="100" bind:value={minProbFilterPct} /> {minProbFilterPct}%</label>
        </div>
        <ul class="signals-list">
          {#each filteredSignals as s}
            <li class="signal-item" class:high={s.prob_reversal_rule >= 0.5}>
              <span>{Math.round(s.prob_reversal_rule * 100)}%</span>
              <span>bars: {s.reversal_horizon_bars}</span>
              <span>{s.expected_move_range[0]}–{s.expected_move_range[1]}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
    <div class="row">
      <span>Horizon</span>
      <span>{lastSignal ? lastSignal.reversal_horizon_bars : '--'}</span>
    </div>
    <div class="row">
      <span>Range</span>
      <span>{lastSignal ? `${lastSignal.expected_move_range[0]}–${lastSignal.expected_move_range[1]}` : '--'}</span>
    </div>
  </aside>
</div>

<style>
  .trend-ai { display: grid; grid-template-columns: 1fr 260px; gap: 8px; height: 100%; position: relative; }
  .trend-settings-btn { position: absolute; top: 4px; right: 270px; padding: 2px 6px; font-size: 12px; background: #111; border: 1px solid var(--border); color: var(--text); cursor: pointer; z-index: 5; }
  .trend-settings { position: absolute; top: 28px; right: 270px; background: var(--bg-panel); border: 1px solid var(--border-strong); padding: 8px; z-index: 20; display: flex; flex-direction: column; gap: 4px; font-size: 11px; }
  .trend-settings label { display: flex; align-items: center; gap: 6px; }
  .charts { display: flex; flex-direction: column; gap: 8px; }
  .legend { font-size: 10px; color: var(--text-muted); padding: 4px 0 0 8px; display: flex; gap: 12px; }
  .leg { font-variant-numeric: tabular-nums; }
  .ai-panel { padding: 8px; }
  .row { display: flex; justify-content: space-between; padding: 4px 0; }
  .row.up span:last-child { color: var(--buy); }
  .row.down span:last-child { color: var(--sell); }
  .row.high span:last-child { color: var(--accent); }
  .signals-block { margin: 8px 0; }
  .signals-toggle { width: 100%; padding: 4px; background: #0a0a0a; border: 1px solid var(--border); color: var(--text); cursor: pointer; text-align: left; }
  .signals-filter { padding: 4px 0; font-size: 10px; }
  .signals-filter input[type="range"] { width: 80px; }
  .signals-list { list-style: none; padding: 0; margin: 4px 0; max-height: 120px; overflow-y: auto; font-size: 11px; }
  .signal-item { display: flex; justify-content: space-between; gap: 8px; padding: 2px 0; }
  .signal-item.high { color: var(--accent); }
  canvas { display: block; background: #050505; }
</style>
