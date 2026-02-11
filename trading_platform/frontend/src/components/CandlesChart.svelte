<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { formatPrice } from '../lib/format'

  export let candles: Array<{ start: number; open: number; high: number; low: number; close: number; volume: number }> = []
  export let trades: Array<{ side: string; price: number; size: number; ts: number }> = []
  export let width: number = 800
  export let height: number = 400

  let canvas: HTMLCanvasElement
  let ctx: CanvasRenderingContext2D | null = null
  let scaleX = 1
  let scaleY = 1
  let offsetX = 0
  let offsetY = 0
  let isDragging = false
  let dragStart = { x: 0, y: 0 }

  $: if (canvas && candles.length > 0) {
    draw()
  }

  onMount(() => {
    if (canvas) {
      ctx = canvas.getContext('2d')
      canvas.width = width
      canvas.height = height
      draw()
    }
  })

  function draw() {
    if (!ctx || !canvas || candles.length === 0) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Calculate price range
    const prices = candles.flatMap(c => [c.high, c.low])
    const minPrice = Math.min(...prices)
    const maxPrice = Math.max(...prices)
    const priceRange = maxPrice - minPrice || 1
    const padding = priceRange * 0.1

    // Calculate time range
    const times = candles.map(c => c.start)
    const minTime = Math.min(...times)
    const maxTime = Math.max(...times)
    const timeRange = maxTime - minTime || 1

    // Draw candles
    const candleWidth = (canvas.width / candles.length) * 0.8
    const priceScale = (canvas.height - 40) / (priceRange + padding * 2)

    candles.forEach((candle, i) => {
      const x = (i / candles.length) * canvas.width + candleWidth / 2
      const openY = canvas.height - 20 - (candle.open - minPrice + padding) * priceScale
      const closeY = canvas.height - 20 - (candle.close - minPrice + padding) * priceScale
      const highY = canvas.height - 20 - (candle.high - minPrice + padding) * priceScale
      const lowY = canvas.height - 20 - (candle.low - minPrice + padding) * priceScale

      const isGreen = candle.close >= candle.open
      ctx.strokeStyle = isGreen ? '#10b981' : '#ef4444'
      ctx.fillStyle = isGreen ? '#10b981' : '#ef4444'
      ctx.lineWidth = 1

      // Wick
      ctx.beginPath()
      ctx.moveTo(x, highY)
      ctx.lineTo(x, lowY)
      ctx.stroke()

      // Body
      const bodyTop = Math.min(openY, closeY)
      const bodyHeight = Math.abs(closeY - openY) || 1
      ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
    })

    // Draw trades overlay
    if (trades.length > 0) {
      trades.forEach(trade => {
        const priceY = canvas.height - 20 - (trade.price - minPrice + padding) * priceScale
        const candleIndex = candles.findIndex(c => c.start <= trade.ts && trade.ts < c.start + 60000)
        if (candleIndex >= 0) {
          const x = (candleIndex / candles.length) * canvas.width + candleWidth / 2
          ctx.fillStyle = (trade.side || '').toLowerCase() === 'buy' ? '#10b981' : '#ef4444'
          ctx.beginPath()
          ctx.arc(x, priceY, Math.min(4, trade.size / 10), 0, Math.PI * 2)
          ctx.fill()
        }
      })
    }

    // Draw price labels
    ctx.fillStyle = '#888'
    ctx.font = '10px monospace'
    ctx.textAlign = 'right'
    for (let i = 0; i <= 5; i++) {
      const price = minPrice + padding + (priceRange / 5) * i
      const y = canvas.height - 20 - (price - minPrice + padding) * priceScale
      ctx.fillText(formatPrice(price, 2), canvas.width - 5, y + 3)
    }
  }

  function handleWheel(e: WheelEvent) {
    e.preventDefault()
    // Zoom logic here if needed
    draw()
  }

  function handleMouseDown(e: MouseEvent) {
    isDragging = true
    dragStart = { x: e.clientX, y: e.clientY }
  }

  function handleMouseMove(e: MouseEvent) {
    if (isDragging) {
      // Pan logic here if needed
      draw()
    }
  }

  function handleMouseUp() {
    isDragging = false
  }
</script>

<div class="chart-container">
  <canvas
    bind:this={canvas}
    {width}
    {height}
    on:wheel={handleWheel}
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:mouseup={handleMouseUp}
    on:mouseleave={handleMouseUp}
  ></canvas>
</div>

<style>
  .chart-container {
    width: 100%;
    height: 100%;
    background: var(--bg-panel, #0a0a0a);
  }

  canvas {
    display: block;
    cursor: crosshair;
  }
</style>
