<script lang="ts">
  import { onMount } from 'svelte'
  export let trendScores: Array<{ ts: number; trend_power: number; trend_power_delta: number }> = []
  export let exhaustionScores: Array<{ ts: number; exhaustion_score: number; absorption_score: number }> = []
  export let ruleSignals: Array<{ ts: number; prob_reversal_rule: number; reversal_horizon_bars: number; expected_move_range: [number, number] }> = []

  let canvasTrend: HTMLCanvasElement
  let canvasExh: HTMLCanvasElement
  let ctxTrend: CanvasRenderingContext2D | null = null
  let ctxExh: CanvasRenderingContext2D | null = null

  const maxPoints = 120
  const paddingLeft = 44
  const paddingBottom = 18
  const paddingRight = 8
  const paddingTop = 8

  $: trend = trendScores.slice(-maxPoints)
  $: exh = exhaustionScores.slice(-maxPoints)
  $: lastSignal = ruleSignals[ruleSignals.length - 1]
  $: latestTrend = trend[trend.length - 1]
  $: latestExh = exh[exh.length - 1]

  $: trendPowerVals = trend.map(t => t.trend_power)
  $: trendDeltaVals = trend.map(t => t.trend_power_delta)
  $: exhVals = exh.map(e => e.exhaustion_score)
  $: absVals = exh.map(e => e.absorption_score)

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
    if (ctxTrend && trend.length) {
      drawChart(
        ctxTrend,
        [
          { values: trendPowerVals, color: '#0d9488' },
          { values: trendDeltaVals, color: '#a855f7' },
        ],
        trend.map(t => t.ts)
      )
    } else if (ctxTrend) {
      ctxTrend.fillStyle = '#050505'
      ctxTrend.fillRect(0, 0, ctxTrend.canvas.width, ctxTrend.canvas.height)
    }
    if (ctxExh && exh.length) {
      drawChart(
        ctxExh,
        [
          { values: exhVals, color: '#f59e0b' },
          { values: absVals, color: '#ef4444' },
        ],
        exh.map(e => e.ts)
      )
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
  <div class="charts">
    <div class="panel">
      <div class="panel-title">TrendPower / ΔTrendPower</div>
      <canvas bind:this={canvasTrend} width={800} height={160} style="width: 100%; height: 160px;"></canvas>
      <div class="legend">
        <span class="leg" style="color: #0d9488;">— TrendPower</span>
        <span class="leg" style="color: #a855f7;">— ΔTrendPower</span>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">Exhaustion / Absorption</div>
      <canvas bind:this={canvasExh} width={800} height={120} style="width: 100%; height: 120px;"></canvas>
      <div class="legend">
        <span class="leg" style="color: #f59e0b;">— Exhaustion</span>
        <span class="leg" style="color: #ef4444;">— Absorption</span>
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
    <div class="row" class:high={lastSignal != null && lastSignal.prob_reversal_rule >= 0.5}>
      <span>Rule reversal</span>
      <span>{lastSignal ? Math.round(lastSignal.prob_reversal_rule * 100) + '%' : '--'}</span>
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
  .trend-ai { display: grid; grid-template-columns: 1fr 260px; gap: 8px; height: 100%; }
  .charts { display: flex; flex-direction: column; gap: 8px; }
  .legend { font-size: 10px; color: var(--text-muted); padding: 4px 0 0 8px; display: flex; gap: 12px; }
  .leg { font-variant-numeric: tabular-nums; }
  .ai-panel { padding: 8px; }
  .row { display: flex; justify-content: space-between; padding: 4px 0; }
  .row.up span:last-child { color: var(--buy); }
  .row.down span:last-child { color: var(--sell); }
  .row.high span:last-child { color: var(--accent); }
  canvas { display: block; background: #050505; }
</style>
