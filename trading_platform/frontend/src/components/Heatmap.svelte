<script lang="ts">
  import { onMount } from 'svelte'
  export let slices: Array<{ ts: number; rows: Array<{ price: number; vol_bid: number; vol_ask: number }> }> = []
  let canvas: HTMLCanvasElement
  let ctx: CanvasRenderingContext2D | null = null

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

  function draw() {
    if (!ctx || !canvas) return
    const w = canvas.width
    const h = canvas.height
    ctx.fillStyle = '#050505'
    ctx.fillRect(0, 0, w, h)
    if (!prices.length || !rowsByTs.length) return
    const nX = rowsByTs.length
    const nY = prices.length
    const priceMin = prices[0]
    const priceMax = prices[prices.length - 1]
    const priceRange = priceMax - priceMin || 1
    const cellW = Math.max(2, w / nX)
    const cellH = Math.max(2, h / nY)
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
        ctx.fillRect(xi * cellW, h - (yi + 1) * cellH, cellW + 1, cellH + 1)
      }
    }
  }

  onMount(() => { ctx = canvas?.getContext('2d') ?? null; draw() })
  $: if (slices.length && canvas) { if (!ctx) ctx = canvas.getContext('2d'); draw() }
</script>

<canvas bind:this={canvas} width={800} height={300} style="width: 100%; height: 100%; min-height: 200px;"></canvas>

<style>
  canvas { display: block; }
</style>
