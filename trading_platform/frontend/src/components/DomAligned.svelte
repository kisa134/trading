<script lang="ts">
  import { onMount } from 'svelte'
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

  $: priceRange = priceMax - priceMin || 1
  $: mid = lastPrice ?? (data?.bids?.[0]?.[0] != null && data?.asks?.[0]?.[0] != null
    ? (data.bids[0][0] + data.asks[0][0]) / 2
    : (priceMin + priceMax) / 2)

  $: bidsFiltered = (data?.bids ?? []).filter(([p]) => p < mid).slice(0, depth)
  $: asksFiltered = (data?.asks ?? []).filter(([p]) => p > mid).slice(0, depth)
  $: maxSize = Math.max(
    ...bidsFiltered.map(([, s]) => s),
    ...asksFiltered.map(([, s]) => s),
    1
  )

  function priceToY(price: number): number {
    const frac = (price - priceMin) / priceRange
    return (1 - frac) * plotH
  }

  function draw() {
    const c = ctx
    if (!c || !canvas) return
    const w = canvas.width
    const h = canvas.height
    c.fillStyle = '#050505'
    c.fillRect(0, 0, w, h)

    const paddingLeft = 4
    const barMaxWidth = 60
    const rowHeight = 14
    const font = '10px "JetBrains Mono", monospace'
    c.font = font

    const midY = priceToY(mid)
    c.strokeStyle = 'rgba(139, 148, 158, 0.8)'
    c.setLineDash([2, 2])
    c.beginPath()
    c.moveTo(0, midY)
    c.lineTo(w, midY)
    c.stroke()
    c.setLineDash([])
    c.fillStyle = '#8b949e'
    c.textAlign = 'left'
    c.textBaseline = 'middle'
    c.fillText(formatPrice(mid), paddingLeft, midY)

    asksFiltered.forEach(([price, size]) => {
      const y = priceToY(price)
      if (y < 0 || y > h) return
      const barW = (size / maxSize) * barMaxWidth
      c.fillStyle = 'rgba(185, 28, 28, 0.4)'
      c.fillRect(w - barMaxWidth - paddingLeft, y - rowHeight / 2, barW, rowHeight)
      c.fillStyle = '#c9d1d9'
      c.textAlign = 'right'
      c.fillText(formatSize(size), w - barMaxWidth - 6, y)
      c.textAlign = 'left'
      c.fillText(formatPrice(price), paddingLeft, y)
    })

    bidsFiltered.forEach(([price, size]) => {
      const y = priceToY(price)
      if (y < 0 || y > h) return
      const barW = (size / maxSize) * barMaxWidth
      c.fillStyle = 'rgba(13, 148, 136, 0.4)'
      c.fillRect(w - barMaxWidth - paddingLeft, y - rowHeight / 2, barW, rowHeight)
      c.fillStyle = '#c9d1d9'
      c.textAlign = 'right'
      c.fillText(formatSize(size), w - barMaxWidth - 6, y)
      c.textAlign = 'left'
      c.fillText(formatPrice(price), paddingLeft, y)
    })
  }

  onMount(() => {
    ctx = canvas?.getContext('2d') ?? null
    if (canvas) {
      canvas.width = width
      canvas.height = plotH
      draw()
    }
  })

  $: if (canvas && ctx && (data || lastPrice != null)) {
    if (canvas.width !== width || canvas.height !== plotH) {
      canvas.width = width
      canvas.height = plotH
    }
    draw()
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
