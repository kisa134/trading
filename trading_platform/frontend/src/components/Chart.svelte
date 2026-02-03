<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { formatPrice, formatTime } from '../lib/format'

  export let candles: Array<{ start: number; open: number; high: number; low: number; close: number; volume: number }> = []
  export let windowStart = 0
  export let windowEnd = 0
  export let onTimeWindowChange: (start: number, end: number) => void = () => {}
  export let mode: 'line' | 'candles' = 'candles'
  export let lineColor = '#38bdf8'
  export let candleUp = '#22d3ee'
  export let candleDown = '#fb7185'
  export let candleWick = '#8b8b8b'

  let container: HTMLDivElement
  let canvas: HTMLCanvasElement
  let ctx: CanvasRenderingContext2D | null = null
  const paddingLeft = 52
  const paddingBottom = 20
  const paddingRight = 8
  const paddingTop = 4
  let plotW = 0
  let plotH = 0
  let isDragging = false
  let lastClientX = 0
  let lastWindowStart = 0
  let lastWindowEnd = 0

  const normalizeTs = (ts: number) => (ts < 10_000_000_000 ? ts * 1000 : ts)

  $: viewCandles = (() => {
    const start = normalizeTs(windowStart)
    const end = normalizeTs(windowEnd)
    return candles.filter((c) => {
      const t = normalizeTs(c.start)
      return t >= start && t <= end
    })
  })()

  $: priceMin = viewCandles.length
    ? Math.min(...viewCandles.map((c) => c.low))
    : 0
  $: priceMax = viewCandles.length
    ? Math.max(...viewCandles.map((c) => c.high))
    : 1
  $: priceRange = priceMax - priceMin || 1

  function draw() {
    if (!ctx || !canvas) return
    const w = canvas.width
    const h = canvas.height
    plotW = w - paddingLeft - paddingRight
    plotH = h - paddingTop - paddingBottom
    ctx.fillStyle = '#050505'
    ctx.fillRect(0, 0, w, h)
    if (!viewCandles.length) return

    const n = viewCandles.length
    const barW = Math.max(1, (plotW / n) * 0.8)
    const gap = Math.max(0, (plotW / n) * 0.2)

    const y = (price: number) =>
      h - paddingBottom - ((price - priceMin) / priceRange) * plotH

    if (mode === 'line') {
      ctx.strokeStyle = lineColor
      ctx.lineWidth = 2
      ctx.beginPath()
      viewCandles.forEach((c, i) => {
        const x = paddingLeft + (i + 0.5) * (plotW / n)
        const cy = y(c.close)
        if (i === 0) ctx.moveTo(x, cy)
        else ctx.lineTo(x, cy)
      })
      ctx.stroke()
    } else {
      viewCandles.forEach((c, i) => {
        const x = paddingLeft + i * (plotW / n) + gap / 2
        const isUp = c.close >= c.open
        ctx.strokeStyle = candleWick
        ctx.fillStyle = isUp ? candleUp : candleDown
        const openY = y(c.open)
        const closeY = y(c.close)
        const highY = y(c.high)
        const lowY = y(c.low)
        ctx.beginPath()
        ctx.moveTo(x + barW / 2, highY)
        ctx.lineTo(x + barW / 2, lowY)
        ctx.stroke()
        const bodyTop = Math.min(openY, closeY)
        const bodyH = Math.max(1, Math.abs(closeY - openY))
        ctx.fillRect(x, bodyTop, barW, bodyH)
        ctx.strokeStyle = isUp ? candleUp : candleDown
        ctx.strokeRect(x, bodyTop, barW, bodyH)
      })
    }

    ctx.fillStyle = '#8b8b8b'
    ctx.font = '10px "JetBrains Mono", monospace'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(formatPrice(priceMax), paddingLeft - 6, paddingTop + 6)
    ctx.fillText(formatPrice(priceMin), paddingLeft - 6, h - paddingBottom - 6)
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    const xStep = Math.max(1, Math.floor(n / 4))
    for (let i = 0; i <= n; i += xStep) {
      const xi = Math.min(i, n - 1)
      const c = viewCandles[xi]
      if (!c) continue
      const x = paddingLeft + (xi + 0.5) * (plotW / n)
      ctx.fillText(formatTime(c.start), x, h - paddingBottom + 4)
    }
  }

  function handleMouseDown(e: MouseEvent) {
    if (!canvas || !plotW) return
    isDragging = true
    lastClientX = e.clientX
    lastWindowStart = windowStart
    lastWindowEnd = windowEnd
  }

  function handleMouseMove(e: MouseEvent) {
    if (!isDragging || !canvas) return
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
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
    if (!canvas || !plotW || windowEnd <= windowStart) return
    e.preventDefault()
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const mouseX = (e.clientX - rect.left) * scaleX - paddingLeft
    const centerRatio = Math.max(0, Math.min(1, mouseX / plotW))
    const span = windowEnd - windowStart
    const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15
    const newSpan = span * factor
    const minSpan = 5000
    const maxSpan = 30 * 24 * 60 * 60 * 1000
    const clampedSpan = Math.max(minSpan, Math.min(maxSpan, newSpan))
    const centerTime = windowStart + centerRatio * span
    const newStart = centerTime - centerRatio * clampedSpan
    const newEnd = centerTime + (1 - centerRatio) * clampedSpan
    onTimeWindowChange(newStart, newEnd)
  }

  let ro: ResizeObserver | null = null
  onMount(() => {
    ctx = canvas?.getContext('2d') ?? null
    function doResize() {
      if (!container || !canvas) return
      const rect = container.getBoundingClientRect()
      canvas.width = Math.floor(rect.width)
      canvas.height = Math.max(120, Math.floor(rect.height))
      draw()
    }
    doResize()
    ro = new ResizeObserver(doResize)
    ro.observe(container)
  })
  onDestroy(() => {
    ro?.disconnect()
  })
  $: if (candles.length && canvas && ctx) draw()
</script>

<div class="chart-wrap" bind:this={container}>
  <canvas
    bind:this={canvas}
    class="chart-canvas"
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseout={handleMouseUp}
    on:wheel={handleWheel}
    role="img"
    aria-label="Price chart, drag to pan, scroll to zoom"
  ></canvas>
</div>

<style>
  .chart-wrap {
    width: 100%;
    min-height: 120px;
    position: relative;
  }
  .chart-canvas {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 120px;
  }
</style>
