<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { formatPrice, formatTime } from '../lib/format'
  export let slices: Array<{ ts: number; rows: Array<{ price: number; vol_bid: number; vol_ask: number }> }> = []
  let container: HTMLDivElement
  let canvas: HTMLCanvasElement
  let ctx: CanvasRenderingContext2D | null = null

  const paddingLeft = 52
  const paddingBottom = 20
  const paddingRight = 8
  const paddingTop = 4

  let tooltip: { price: number; ts: number; vol_bid: number; vol_ask: number; x: number; y: number } | null = null
  let cellW = 0
  let cellH = 0
  let plotW = 0
  let plotH = 0

  $: rowsByTs = slices.map((s: { ts: number; rows?: Array<{ price: number; vol_bid: number; vol_ask: number }> }) => ({ ts: s.ts, rows: s.rows || [] })).filter((x: { rows: unknown[] }) => x.rows.length)
  $: prices = (() => {
    const set = new Set<number>()
    rowsByTs.forEach(({ rows }: { rows: Array<{ price: number }> }) => rows.forEach(r => set.add(r.price)))
    return [...set].sort((a, b) => a - b)
  })()
  $: maxVol = (() => {
    let m = 0
    rowsByTs.forEach(({ rows }: { rows: Array<{ vol_bid: number; vol_ask: number }> }) => rows.forEach(r => { m = Math.max(m, r.vol_bid + r.vol_ask) }))
    return m || 1
  })()

  function getCellAt(offsetX: number, offsetY: number): { xi: number; yi: number } | null {
    const x = offsetX - paddingLeft
    const y = offsetY - paddingTop
    if (x < 0 || y < 0 || x >= plotW || y >= plotH) return null
    const xi = Math.floor(x / cellW)
    const yi = Math.floor((plotH - y) / cellH)
    const nX = rowsByTs.length
    const nY = prices.length
    if (xi < 0 || xi >= nX || yi < 0 || yi >= nY) return null
    return { xi, yi }
  }

  function handleMouseMove(e: MouseEvent) {
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const ox = (e.clientX - rect.left) * scaleX
    const oy = (e.clientY - rect.top) * scaleY
    const cell = getCellAt(ox, oy)
    if (!cell) {
      tooltip = null
      return
    }
    const slice = rowsByTs[cell.xi]
    const price = prices[cell.yi]
    const rowMap = new Map(slice.rows.map((r: { price: number; vol_bid: number; vol_ask: number }) => [r.price, r]))
    const r = rowMap.get(price)
    tooltip = {
      price,
      ts: slice.ts,
      vol_bid: r?.vol_bid ?? 0,
      vol_ask: r?.vol_ask ?? 0,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    }
  }

  function handleMouseLeave() {
    tooltip = null
  }

  function draw() {
    if (!ctx || !canvas) return
    const w = canvas.width
    const h = canvas.height
    ctx.fillStyle = '#050505'
    ctx.fillRect(0, 0, w, h)
    if (!prices.length || !rowsByTs.length) return

    const nX = rowsByTs.length
    const nY = prices.length
    plotW = w - paddingLeft - paddingRight
    plotH = h - paddingTop - paddingBottom
    cellW = Math.max(2, plotW / nX)
    cellH = Math.max(2, plotH / nY)
    const volScale = 1 / Math.log(maxVol + 1)

    for (let xi = 0; xi < nX; xi++) {
      const slice = rowsByTs[xi]
      const rowMap = new Map(slice.rows.map((r: { price: number; vol_bid: number; vol_ask: number }) => [r.price, r]))
      for (let yi = 0; yi < nY; yi++) {
        const price = prices[yi]
        const r = rowMap.get(price) as { vol_bid: number; vol_ask: number } | undefined
        const vol = r ? r.vol_bid + r.vol_ask : 0
        const intensity = Math.min(1, Math.log(vol + 1) * volScale)
        const green = r?.vol_bid ? Math.round(80 + intensity * 80) : 0
        const red = r?.vol_ask ? Math.round(80 + intensity * 80) : 0
        ctx.fillStyle = `rgb(${red}, ${green}, 60)`
        const px = paddingLeft + xi * cellW
        const py = paddingTop + (nY - 1 - yi) * cellH
        ctx.fillRect(px, py, cellW + 1, cellH + 1)
      }
    }

    ctx.fillStyle = '#8b8b8b'
    ctx.font = '10px "JetBrains Mono", monospace'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    const yStep = Math.max(1, Math.floor(nY / 6))
    for (let i = 0; i <= nY; i += yStep) {
      const yi = i === nY ? nY - 1 : i
      const price = prices[yi]
      const y = paddingTop + (nY - 1 - yi) * cellH + cellH / 2
      ctx.fillText(formatPrice(price), paddingLeft - 6, y)
    }
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    const xStep = Math.max(1, Math.floor(nX / 4))
    for (let i = 0; i <= nX; i += xStep) {
      const xi = Math.min(i, nX - 1)
      const ts = rowsByTs[xi]?.ts
      if (ts == null) continue
      const x = paddingLeft + xi * cellW + cellW / 2
      ctx.fillText(formatTime(ts), x, h - paddingBottom + 4)
    }
  }

  let ro: ResizeObserver | null = null
  onMount(() => {
    ctx = canvas?.getContext('2d') ?? null
    function doResize() {
      if (!container || !canvas) return
      const rect = container.getBoundingClientRect()
      canvas.width = Math.floor(rect.width)
      canvas.height = Math.max(200, Math.floor(rect.height))
      draw()
    }
    doResize()
    ro = new ResizeObserver(doResize)
    ro.observe(container)
  })
  onDestroy(() => {
    ro?.disconnect()
  })
  $: if (slices.length && canvas && ctx) draw()
</script>

<div class="heatmap-wrap" bind:this={container}>
  <canvas
    bind:this={canvas}
    class="heatmap-canvas"
    on:mousemove={handleMouseMove}
    on:mouseleave={handleMouseLeave}
  ></canvas>
  {#if tooltip}
    <div class="tooltip" style="left: {tooltip.x + 12}px; top: {tooltip.y + 8}px;">
      <div>Price: {formatPrice(tooltip.price)}</div>
      <div>Time: {formatTime(tooltip.ts)}</div>
      <div class="bid">Bid vol: {tooltip.vol_bid.toFixed(0)}</div>
      <div class="ask">Ask vol: {tooltip.vol_ask.toFixed(0)}</div>
    </div>
  {/if}
</div>
<div class="legend">Green = bid volume · Red = ask volume</div>

<style>
  .heatmap-wrap { position: relative; width: 100%; min-height: 200px; }
  .heatmap-canvas { display: block; width: 100%; height: 100%; min-height: 200px; }
  .tooltip {
    position: absolute;
    pointer-events: none;
    background: #0a0a0a;
    border: 1px solid var(--border-strong);
    padding: 6px 8px;
    font-size: 11px;
    z-index: 10;
    white-space: nowrap;
  }
  .tooltip .bid { color: var(--buy); }
  .tooltip .ask { color: var(--sell); }
  .legend { font-size: 10px; color: var(--text-muted); padding: 4px 0 0 4px; }
</style>
