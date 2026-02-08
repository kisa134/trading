<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { formatPrice, formatTime } from '../lib/format'

  export let slices: Array<{ ts: number; rows: Array<{ price: number; vol_bid: number; vol_ask: number }> }> = []
  export let candles: Array<{ start: number; open: number; high: number; low: number; close: number; volume: number }> = []
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

  $: priceMin = (() => {
    const fromHeat = heatmapPrices.length ? Math.min(...heatmapPrices) : null
    if (candlePriceMin != null && fromHeat != null) return Math.min(candlePriceMin, fromHeat)
    return candlePriceMin ?? fromHeat ?? 0
  })()

  $: priceMax = (() => {
    const fromHeat = heatmapPrices.length ? Math.max(...heatmapPrices) : null
    if (candlePriceMax != null && fromHeat != null) return Math.max(candlePriceMax, fromHeat)
    return candlePriceMax ?? fromHeat ?? 1
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

  function hexToRgb(hex: string): [number, number, number] {
    const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i)
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 128, 0]
  }
  $: rgbBid = hexToRgb(colorBid)
  $: rgbAsk = hexToRgb(colorAsk)

  function drawHeatmap() {
    if (!heatmapCtx || !heatmapCanvas) return
    const w = heatmapCanvas.width
    const h = heatmapCanvas.height
    plotW = w - paddingLeft - paddingRight
    plotH = h - paddingTop - paddingBottom
    heatmapCtx.fillStyle = '#050505'
    heatmapCtx.fillRect(0, 0, w, h)
    if (!heatmapPrices.length || !rowsByTs.length) return

    const nX = rowsByTs.length
    const nY = heatmapPrices.length
    const cellW = Math.max(2, plotW / nX)
    const volScale = 1 / Math.log(maxVolHeat + 1)

    for (let xi = 0; xi < nX; xi++) {
      const slice = rowsByTs[xi]
      const rowMap = new Map(slice.rows.map((r) => [r.price, r]))
      for (let yi = 0; yi < nY; yi++) {
        const price = heatmapPrices[yi]
        const r = rowMap.get(price)
        const vol = r ? (showBid ? r.vol_bid : 0) + (showAsk ? r.vol_ask : 0) : 0
        const intensity = Math.min(1, Math.log(vol + 1) * volScale)
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
          const ts = rowsByTs[xi]?.ts
          if (ts == null) continue
          const x = paddingLeft + xi * cellW + cellW / 2
          heatmapCtx.fillText(formatTime(ts), x, h - paddingBottom + 4)
        }
      }
    }
  }

  function drawBubbles() {
    if (!bubblesCtx || !bubblesCanvas || !viewCandles.length) return
    bubblesCtx.clearRect(0, 0, bubblesCanvas.width, bubblesCanvas.height)
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
    const scaleX = heatmapCanvas.width / rect.width
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
    const scaleX = heatmapCanvas.width / rect.width
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

  function resize() {
    if (!container || !heatmapCanvas || !bubblesCanvas) return
    const rect = container.getBoundingClientRect()
    const width = Math.floor(rect.width)
    const height = Math.max(200, Math.floor(rect.height))
    heatmapCanvas.width = width
    heatmapCanvas.height = height
    heatmapCanvas.style.width = width + 'px'
    heatmapCanvas.style.height = height + 'px'
    bubblesCanvas.width = width
    bubblesCanvas.height = height
    bubblesCanvas.style.width = width + 'px'
    bubblesCanvas.style.height = height + 'px'
    plotW = width - paddingLeft - paddingRight
    plotH = height - paddingTop - paddingBottom
    drawHeatmap()
    drawBubbles()
    notifyScale()
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

  $: if (slices.length || candles.length) {
    if (heatmapCtx && heatmapCanvas) drawHeatmap()
    if (bubblesCtx && bubblesCanvas) drawBubbles()
    if (plotH > 0) notifyScale()
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
