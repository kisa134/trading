<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { formatPrice, formatTime } from '../lib/format'

  export let slices: Array<{ ts: number; rows: Array<{ price: number; vol_bid: number; vol_ask: number }> }> = []
  export let candles: Array<{ start: number; open: number; high: number; low: number; close: number; volume: number }> = []
  export let trades: Array<{ ts: number; price: number; size: number; side: string }> = []
  export let bubbleMode: 'off' | 'candles' | 'trades' = 'candles'
  export let windowStart = 0
  export let windowEnd = 0
  export let onTimeWindowChange: (start: number, end: number) => void = () => {}
  export let onScaleChange: (info: { priceMin: number; priceMax: number; plotH: number }) => void = () => {}
  export let colorBid = '#0d9488'
  export let colorAsk = '#b91c1c'
  export let bubbleUp = 'rgba(34, 197, 94, 0.6)'
  export let bubbleDown = 'rgba(248, 81, 73, 0.6)'
  export let showBid = true
  export let showAsk = true
  export let showPriceLabels = true
  export let showTimeLabels = true

  let container: HTMLDivElement
  let heatmapCanvas: HTMLCanvasElement
  let bubblesCanvas: HTMLCanvasElement
  let heatmapCtx: CanvasRenderingContext2D | null = null
  let bubblesCtx: CanvasRenderingContext2D | null = null

  const paddingLeft = 52
  const paddingBottom = 20
  const paddingRight = 8
  const paddingTop = 4

  const normalizeTs = (ts: number) => (ts < 10_000_000_000 ? ts * 1000 : ts)
  const MIN_SPAN = 5000
  const MAX_SPAN = 30 * 24 * 60 * 60 * 1000

  let plotW = 0
  let plotH = 0
  let isDragging = false
  let lastClientX = 0
  let lastWindowStart = 0
  let lastWindowEnd = 0
  let pendingRedraw = false
  const dpr = typeof window !== 'undefined' ? Math.min(2, window.devicePixelRatio || 1) : 1

  $: winStart = normalizeTs(windowStart)
  $: winEnd = normalizeTs(windowEnd)

  $: rowsByTs = slices
    .map((s) => ({ ts: s.ts, rows: s.rows || [] }))
    .filter((x) => x.rows.length)
    .filter((s) => {
      const t = normalizeTs(s.ts)
      return t >= winStart && t <= winEnd
    })

  $: viewCandles = candles.filter((c) => {
    const t = normalizeTs(c.start)
    return t >= winStart && t <= winEnd
  })

  $: heatmapPrices = (() => {
    const set = new Set<number>()
    rowsByTs.forEach(({ rows }) => rows.forEach((r) => set.add(r.price)))
    return [...set].sort((a, b) => a - b)
  })()

  $: candlePriceMin = viewCandles.length ? Math.min(...viewCandles.map((c) => c.low)) : null
  $: candlePriceMax = viewCandles.length ? Math.max(...viewCandles.map((c) => c.high)) : null
  $: tradePriceMin = viewTrades.length ? Math.min(...viewTrades.map((t) => t.price)) : null
  $: tradePriceMax = viewTrades.length ? Math.max(...viewTrades.map((t) => t.price)) : null

  $: priceMin = (() => {
    const fromHeat = heatmapPrices.length ? Math.min(...heatmapPrices) : null
    let lo = candlePriceMin ?? fromHeat ?? tradePriceMin
    if (tradePriceMin != null && lo != null) lo = Math.min(lo, tradePriceMin)
    else if (tradePriceMin != null) lo = tradePriceMin
    return lo ?? 0
  })()

  $: priceMax = (() => {
    const fromHeat = heatmapPrices.length ? Math.max(...heatmapPrices) : null
    let hi = candlePriceMax ?? fromHeat ?? tradePriceMax
    if (tradePriceMax != null && hi != null) hi = Math.max(hi, tradePriceMax)
    else if (tradePriceMax != null) hi = tradePriceMax
    return hi ?? 1
  })()

  $: priceRange = priceMax - priceMin || 1
  $: timeSpan = winEnd - winStart || 1

  function timeToX(ts: number): number {
    const t = normalizeTs(ts)
    const frac = (t - winStart) / timeSpan
    return paddingLeft + frac * plotW
  }

  function priceToY(price: number): number {
    const frac = (price - priceMin) / priceRange
    return paddingTop + (1 - frac) * plotH
  }

  $: maxVolHeat = (() => {
    let m = 0
    rowsByTs.forEach(({ rows }) =>
      rows.forEach((r) => {
        m = Math.max(m, r.vol_bid + r.vol_ask)
      })
    )
    return m || 1
  })()

  $: maxVolBubbles = viewCandles.length
    ? Math.max(...viewCandles.map((c) => c.volume), 1)
    : 1

  $: viewTrades = (() => {
    if (!trades.length) return []
    const winS = winStart
    const winE = winEnd
    const norm = (ts: number) => (ts < 10_000_000_000 ? ts * 1000 : ts)
    return trades.filter((t) => {
      const tt = norm(t.ts)
      return tt >= winS && tt <= winE
    })
  })()

  $: maxTradeSize = viewTrades.length ? Math.max(...viewTrades.map((t) => t.size), 1) : 1
  const BUBBLES_DECIMATION_MAX = 800

  function hexToRgb(hex: string): [number, number, number] {
    const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i)
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 128, 0]
  }
  $: rgbBid = hexToRgb(colorBid)
  $: rgbAsk = hexToRgb(colorAsk)

  const HEATMAP_INTENSITY_THRESHOLD = 0.03

  function drawHeatmap() {
    if (!heatmapCtx || !heatmapCanvas) return
    const w = heatmapCanvas.width / dpr
    const h = heatmapCanvas.height / dpr
    plotW = w - paddingLeft - paddingRight
    plotH = h - paddingTop - paddingBottom
    heatmapCtx.fillStyle = '#0a0a0a'
    heatmapCtx.fillRect(0, 0, w, h)
    if (!heatmapPrices.length || !rowsByTs.length) return

    const maxCols = Math.min(rowsByTs.length, Math.max(1, Math.floor(plotW)))
    const slicesToDraw = rowsByTs.slice(-maxCols)
    const nX = slicesToDraw.length
    const nY = heatmapPrices.length
    const cellW = Math.max(1, plotW / nX)
    const volScale = 1 / Math.log(maxVolHeat + 1)

    for (let xi = 0; xi < nX; xi++) {
      const slice = slicesToDraw[xi]
      const rowMap = new Map(slice.rows.map((r) => [r.price, r]))
      for (let yi = 0; yi < nY; yi++) {
        const price = heatmapPrices[yi]
        const r = rowMap.get(price)
        const vol = r ? (showBid ? r.vol_bid : 0) + (showAsk ? r.vol_ask : 0) : 0
        const intensity = Math.min(1, Math.log(vol + 1) * volScale)
        if (intensity < HEATMAP_INTENSITY_THRESHOLD) continue
        const bidInt = showBid && r?.vol_bid ? intensity : 0
        const askInt = showAsk && r?.vol_ask ? intensity : 0
        const r_ = Math.round(40 + askInt * (rgbAsk[0] - 40))
        const g_ = Math.round(40 + bidInt * (rgbBid[1] - 40))
        const b_ = Math.round(40 + (bidInt * rgbBid[2] + askInt * rgbAsk[2]) / 2)
        heatmapCtx.fillStyle = `rgb(${r_}, ${g_}, ${b_})`
        const px = paddingLeft + xi * cellW
        const cellTop = priceToY(price)
        const cellBottom = yi === 0 ? paddingTop + plotH : priceToY(heatmapPrices[yi - 1])
        const cellH = Math.max(1, cellBottom - cellTop)
        heatmapCtx.fillRect(px, cellTop, cellW + 1, cellH)
      }
    }

    if (showPriceLabels || showTimeLabels) {
      heatmapCtx.fillStyle = '#8b8b8b'
      heatmapCtx.font = '10px "JetBrains Mono", monospace'
      if (showPriceLabels) {
        heatmapCtx.textAlign = 'right'
        heatmapCtx.textBaseline = 'middle'
        for (let i = 0; i <= 5; i++) {
          const p = priceMin + (priceMax - priceMin) * (1 - i / 5)
          const y = paddingTop + (i / 5) * plotH
          heatmapCtx.fillText(formatPrice(p), paddingLeft - 6, y)
        }
      }
      if (showTimeLabels) {
        heatmapCtx.textAlign = 'center'
        heatmapCtx.textBaseline = 'top'
        const xStep = Math.max(1, Math.floor(nX / 4))
        for (let i = 0; i <= nX; i += xStep) {
          const xi = Math.min(i, nX - 1)
          const ts = slicesToDraw[xi]?.ts
          if (ts == null) continue
          const x = paddingLeft + xi * cellW + cellW / 2
          heatmapCtx.fillText(formatTime(ts), x, h - paddingBottom + 4)
        }
      }
    }
  }

  function drawBubbles() {
    if (!bubblesCtx || !bubblesCanvas) return
    const w = bubblesCanvas.width / dpr
    const h = bubblesCanvas.height / dpr
    bubblesCtx.clearRect(0, 0, w, h)
    if (bubbleMode === 'off') return

    if (bubbleMode === 'candles' && viewCandles.length) {
      const minR = 2
      const maxR = Math.min(plotW / Math.max(viewCandles.length, 1) * 0.8, 24)
      const volScale = maxVolBubbles > 0 ? 1 / maxVolBubbles : 0
      viewCandles.forEach((c) => {
        const x = timeToX(c.start)
        const y = priceToY(c.close)
        const r = Math.max(minR, Math.sqrt(c.volume * volScale) * maxR)
        const isUp = c.close >= c.open
        bubblesCtx!.fillStyle = isUp ? bubbleUp : bubbleDown
        bubblesCtx!.beginPath()
        bubblesCtx!.arc(x, y, r, 0, Math.PI * 2)
        bubblesCtx!.fill()
      })
      return
    }

    if (bubbleMode === 'trades' && viewTrades.length) {
      let toDraw = viewTrades
      if (toDraw.length > BUBBLES_DECIMATION_MAX) {
        const step = Math.ceil(toDraw.length / BUBBLES_DECIMATION_MAX)
        toDraw = toDraw.filter((_, i) => i % step === 0)
      }
      const minR = 1.5
      const maxR = 8
      const sizeScale = maxTradeSize > 0 ? 1 / maxTradeSize : 0
      toDraw.forEach((t) => {
        const x = timeToX(t.ts)
        const y = priceToY(t.price)
        const r = Math.max(minR, Math.sqrt(t.size * sizeScale) * maxR)
        const isBuy = (t.side || '').toLowerCase().startsWith('b')
        bubblesCtx!.fillStyle = isBuy ? bubbleUp : bubbleDown
        bubblesCtx!.beginPath()
        bubblesCtx!.arc(x, y, r, 0, Math.PI * 2)
        bubblesCtx!.fill()
      })
    }
  }

  function notifyScale() {
    onScaleChange({ priceMin, priceMax, plotH })
  }

  function handleMouseDown(e: MouseEvent) {
    if (!heatmapCanvas || !plotW) return
    isDragging = true
    lastClientX = e.clientX
    lastWindowStart = windowStart
    lastWindowEnd = windowEnd
  }

  function handleMouseMove(e: MouseEvent) {
    if (!isDragging || !heatmapCanvas) return
    const rect = heatmapCanvas.getBoundingClientRect()
    const scaleX = (heatmapCanvas.width / dpr) / rect.width
    const deltaPx = (e.clientX - lastClientX) * scaleX
    const span = lastWindowEnd - lastWindowStart
    if (span <= 0) return
    const deltaMs = -(deltaPx / plotW) * span
    lastClientX = e.clientX
    lastWindowStart = lastWindowStart + deltaMs
    lastWindowEnd = lastWindowEnd + deltaMs
    onTimeWindowChange(lastWindowStart, lastWindowEnd)
  }

  function handleMouseUp() {
    isDragging = false
  }

  function handleWheel(e: WheelEvent) {
    if (!heatmapCanvas || !plotW || windowEnd <= windowStart) return
    e.preventDefault()
    const rect = heatmapCanvas.getBoundingClientRect()
    const scaleX = (heatmapCanvas.width / dpr) / rect.width
    const mouseX = (e.clientX - rect.left) * scaleX - paddingLeft
    const centerRatio = Math.max(0, Math.min(1, mouseX / plotW))
    const span = windowEnd - windowStart
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15
    const newSpan = span * factor
    const clampedSpan = Math.max(MIN_SPAN, Math.min(MAX_SPAN, newSpan))
    const centerTime = windowStart + centerRatio * span
    const newStart = centerTime - centerRatio * clampedSpan
    const newEnd = centerTime + (1 - centerRatio) * clampedSpan
    onTimeWindowChange(newStart, newEnd)
  }

  function scheduleDraw() {
    if (pendingRedraw) return
    pendingRedraw = true
    requestAnimationFrame(() => {
      pendingRedraw = false
      if (heatmapCtx && heatmapCanvas) drawHeatmap()
      if (bubblesCtx && bubblesCanvas) drawBubbles()
      const hasData = rowsByTs.length > 0 || viewCandles.length > 0 || viewTrades.length > 0
      if (plotH > 0 && hasData) notifyScale()
    })
  }

  /** Expose heatmap canvas for AI snapshot capture (toBlob). */
  export function getHeatmapCanvas(): HTMLCanvasElement | null {
    return heatmapCanvas ?? null
  }

  function resize() {
    if (!container || !heatmapCanvas || !bubblesCanvas) return
    const rect = container.getBoundingClientRect()
    const logicalW = Math.floor(rect.width)
    const logicalH = Math.max(200, Math.floor(rect.height))
    heatmapCanvas.width = logicalW * dpr
    heatmapCanvas.height = logicalH * dpr
    heatmapCanvas.style.width = logicalW + 'px'
    heatmapCanvas.style.height = logicalH + 'px'
    bubblesCanvas.width = logicalW * dpr
    bubblesCanvas.height = logicalH * dpr
    bubblesCanvas.style.width = logicalW + 'px'
    bubblesCanvas.style.height = logicalH + 'px'
    if (heatmapCtx) {
      heatmapCtx.setTransform(1, 0, 0, 1, 0, 0)
      heatmapCtx.scale(dpr, dpr)
    }
    if (bubblesCtx) {
      bubblesCtx.setTransform(1, 0, 0, 1, 0, 0)
      bubblesCtx.scale(dpr, dpr)
    }
    plotW = logicalW - paddingLeft - paddingRight
    plotH = logicalH - paddingTop - paddingBottom
    scheduleDraw()
  }

  let ro: ResizeObserver | null = null
  onMount(() => {
    heatmapCtx = heatmapCanvas?.getContext('2d') ?? null
    bubblesCtx = bubblesCanvas?.getContext('2d') ?? null
    resize()
    ro = new ResizeObserver(resize)
    ro.observe(container)
  })
  onDestroy(() => {
    ro?.disconnect()
  })

  $: if (slices.length || candles.length || trades.length || bubbleMode === 'off') {
    scheduleDraw()
  }
</script>

<div class="wrap" bind:this={container}>
  <canvas
    bind:this={heatmapCanvas}
    class="layer heatmap-layer"
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseout={handleMouseUp}
    on:wheel={handleWheel}
    role="img"
    aria-label="Heatmap with volume bubbles, drag to pan, scroll to zoom"
  ></canvas>
  <canvas
    bind:this={bubblesCanvas}
    class="layer bubbles-layer"
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseout={handleMouseUp}
    on:wheel={handleWheel}
    role="img"
    aria-label="Volume bubbles overlay"
  ></canvas>
</div>

<style>
  .wrap {
    position: relative;
    width: 100%;
    min-height: 200px;
  }
  .layer {
    position: absolute;
    left: 0;
    top: 0;
    display: block;
    width: 100%;
    height: 100%;
    min-height: 200px;
  }
  .heatmap-layer {
    z-index: 0;
  }
  .bubbles-layer {
    z-index: 1;
    pointer-events: none;
  }
  .wrap:has(.bubbles-layer) .heatmap-layer {
    pointer-events: auto;
  }
</style>
