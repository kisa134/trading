<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { formatPrice, formatSize } from '../lib/format'

  export let data: { ts: number; bids: [number, number][]; asks: [number, number][] } | null = null
  export let priceMin = 0
  export let priceMax = 1
  export let plotH = 300
  export let lastPrice: number | null = null
  export let depth = 30
  export let width = 200

  let canvas: HTMLCanvasElement
  let ctx: CanvasRenderingContext2D | null = null
  const dpr = typeof window !== 'undefined' ? Math.min(2, window.devicePixelRatio || 1) : 1

  const ROW_HEIGHT = 20
  const DOM_REDRAW_THROTTLE_MS = 120
  let lastDrawTime = 0
  let throttleTimer: ReturnType<typeof setTimeout> | null = null

  $: priceRange = priceMax - priceMin || 1
  $: mid = lastPrice ?? (data?.bids?.[0]?.[0] != null && data?.asks?.[0]?.[0] != null
    ? (data.bids[0][0] + data.asks[0][0]) / 2
    : (priceMin + priceMax) / 2)

  $: maxVisibleRows = Math.max(3, Math.floor(plotH / ROW_HEIGHT))
  $: maxRowsPerSide = Math.floor(maxVisibleRows / 2)
  $: effectiveDepth = Math.min(depth, maxRowsPerSide)

  $: asksSorted = (data?.asks ?? [])
    .filter(([p]) => p > mid)
    .sort((a, b) => a[0] - b[0])
    .slice(0, effectiveDepth)
  $: bidsSorted = (data?.bids ?? [])
    .filter(([p]) => p < mid)
    .sort((a, b) => b[0] - a[0])
    .slice(0, effectiveDepth)

  function priceToY(price: number): number {
    const frac = (price - priceMin) / priceRange
    return (1 - frac) * plotH
  }

  function filterByMinYStep<T extends [number, number]>(
    items: T[],
    priceToYFn: (p: number) => number,
    _ascendingY: boolean
  ): T[] {
    const out: T[] = []
    let lastY: number | null = null
    for (const item of items) {
      const y = priceToYFn(item[0])
      if (lastY != null && Math.abs(y - lastY) < ROW_HEIGHT) continue
      out.push(item)
      lastY = y
      if (out.length >= maxRowsPerSide) break
    }
    return out
  }

  $: asksToDraw = filterByMinYStep(asksSorted, priceToY, false)
  $: bidsToDraw = filterByMinYStep(bidsSorted, priceToY, true)
  $: maxSize = Math.max(
    ...asksToDraw.map(([, s]) => s),
    ...bidsToDraw.map(([, s]) => s),
    1
  )

  function draw() {
    const c = ctx
    if (!c || !canvas) return
    const w = canvas.width / dpr
    const h = canvas.height / dpr
    c.fillStyle = '#0a0a0a'
    c.fillRect(0, 0, w, h)

    const paddingLeft = 4
    const barMaxWidth = 60
    const rowHeight = ROW_HEIGHT - 2
    const font = '11px "JetBrains Mono", monospace'
    c.font = font

    const midY = priceToY(mid)
    c.strokeStyle = 'rgba(139, 148, 158, 0.9)'
    c.lineWidth = 1
    c.setLineDash([2, 2])
    c.beginPath()
    c.moveTo(0, midY)
    c.lineTo(w, midY)
    c.stroke()
    c.setLineDash([])
    c.fillStyle = '#e6edf3'
    c.textAlign = 'left'
    c.textBaseline = 'middle'
    c.fillText(formatPrice(mid), paddingLeft, midY)

    asksToDraw.forEach(([price, size]) => {
      const y = priceToY(price)
      if (y < 0 || y > h) return
      const barW = (size / maxSize) * barMaxWidth
      c.fillStyle = 'rgba(185, 28, 28, 0.5)'
      c.fillRect(w - barMaxWidth - paddingLeft, y - rowHeight / 2, barW, rowHeight)
      c.fillStyle = '#e6edf3'
      c.textAlign = 'right'
      c.fillText(formatSize(size), w - barMaxWidth - 6, y)
      c.textAlign = 'left'
      c.fillText(formatPrice(price), paddingLeft, y)
    })

    bidsToDraw.forEach(([price, size]) => {
      const y = priceToY(price)
      if (y < 0 || y > h) return
      const barW = (size / maxSize) * barMaxWidth
      c.fillStyle = 'rgba(13, 148, 136, 0.5)'
      c.fillRect(w - barMaxWidth - paddingLeft, y - rowHeight / 2, barW, rowHeight)
      c.fillStyle = '#e6edf3'
      c.textAlign = 'right'
      c.fillText(formatSize(size), w - barMaxWidth - 6, y)
      c.textAlign = 'left'
      c.fillText(formatPrice(price), paddingLeft, y)
    })
  }

  function scheduleDraw() {
    const now = Date.now()
    if (now - lastDrawTime < DOM_REDRAW_THROTTLE_MS) {
      if (throttleTimer == null) {
        throttleTimer = setTimeout(() => {
          throttleTimer = null
          lastDrawTime = Date.now()
          draw()
        }, DOM_REDRAW_THROTTLE_MS - (now - lastDrawTime))
      }
      return
    }
    lastDrawTime = now
    draw()
  }

  onMount(() => {
    ctx = canvas?.getContext('2d') ?? null
    if (canvas && ctx) {
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(plotH * dpr)
      canvas.style.width = width + 'px'
      canvas.style.height = plotH + 'px'
      ctx.scale(dpr, dpr)
      draw()
    }
  })

  onDestroy(() => {
    if (throttleTimer != null) clearTimeout(throttleTimer)
  })

  $: if (canvas && ctx && (data || lastPrice != null)) {
    const cw = Math.floor(width * dpr)
    const ch = Math.floor(plotH * dpr)
    if (canvas.width !== cw || canvas.height !== ch) {
      canvas.width = cw
      canvas.height = ch
      canvas.style.width = width + 'px'
      canvas.style.height = plotH + 'px'
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.scale(dpr, dpr)
    }
    scheduleDraw()
  }
</script>

<div class="dom-aligned">
  <canvas
    bind:this={canvas}
    class="dom-canvas"
    style="width: {width}px; height: {plotH}px;"
    role="img"
    aria-label="Order book aligned to chart price scale"
  ></canvas>
</div>

<style>
  .dom-aligned {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .dom-canvas {
    display: block;
  }
</style>
