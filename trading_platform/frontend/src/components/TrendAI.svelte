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

  $: trend = trendScores.slice(-maxPoints)
  $: exh = exhaustionScores.slice(-maxPoints)
  $: lastSignal = ruleSignals[ruleSignals.length - 1]
  $: latestTrend = trend[trend.length - 1]
  $: latestExh = exh[exh.length - 1]

  function drawLine(ctx: CanvasRenderingContext2D, values: number[], color: string) {
    if (!values.length) return
    const w = ctx.canvas.width
    const h = ctx.canvas.height
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    ctx.strokeStyle = color
    ctx.beginPath()
    values.forEach((v, i) => {
      const x = (i / (values.length - 1)) * w
      const y = h - ((v - min) / range) * h
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
  }

  function redraw() {
    if (ctxTrend) {
      ctxTrend.clearRect(0, 0, ctxTrend.canvas.width, ctxTrend.canvas.height)
      drawLine(ctxTrend, trend.map(t => t.trend_power), '#0d9488')
      drawLine(ctxTrend, trend.map(t => t.trend_power_delta), '#a855f7')
    }
    if (ctxExh) {
      ctxExh.clearRect(0, 0, ctxExh.canvas.width, ctxExh.canvas.height)
      drawLine(ctxExh, exh.map(e => e.exhaustion_score), '#f59e0b')
      drawLine(ctxExh, exh.map(e => e.absorption_score), '#ef4444')
    }
  }

  onMount(() => {
    ctxTrend = canvasTrend.getContext('2d')
    ctxExh = canvasExh.getContext('2d')
    redraw()
  })

  $: if (trend.length || exh.length) redraw()
</script>

<div class="trend-ai">
  <div class="charts">
    <div class="panel">
      <div class="panel-title">TrendPower / ΔTrendPower</div>
      <canvas bind:this={canvasTrend} width={800} height={160} style="width: 100%; height: 160px;"></canvas>
    </div>
    <div class="panel">
      <div class="panel-title">Exhaustion / Absorption</div>
      <canvas bind:this={canvasExh} width={800} height={120} style="width: 100%; height: 120px;"></canvas>
    </div>
  </div>

  <aside class="panel ai-panel">
    <div class="panel-title">AI Trend Engine</div>
    <div class="row">
      <span>TrendPower</span>
      <span>{latestTrend ? latestTrend.trend_power.toFixed(1) : '--'}</span>
    </div>
    <div class="row">
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
    <div class="row">
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
  .ai-panel { padding: 8px; }
  .row { display: flex; justify-content: space-between; padding: 4px 0; }
  canvas { display: block; background: #050505; }
</style>
