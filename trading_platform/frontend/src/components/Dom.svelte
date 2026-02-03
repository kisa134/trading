<script lang="ts">
  import { formatPrice, formatSize } from '../lib/format'
  export let data: { ts: number; bids: [number, number][]; asks: [number, number][] } | null = null
  export let depth = 20
  $: bids = data?.bids?.slice(0, depth) ?? []
  $: asks = data?.asks?.slice(0, depth) ?? []
  $: maxSize = Math.max(
    ...bids.map(([, s]) => s),
    ...asks.map(([, s]) => s),
    1
  )
  $: bestBid = bids[0]?.[0]
  $: bestAsk = asks[0]?.[0]
  $: midPrice = bestBid != null && bestAsk != null ? (bestBid + bestAsk) / 2 : null
  $: spread = bestBid != null && bestAsk != null ? bestAsk - bestBid : null
  $: asksReversed = [...asks].reverse()
</script>

<div class="dom">
  {#if spread != null && midPrice != null}
    <div class="summary">Spread: {formatPrice(spread)} | Mid {formatPrice(midPrice)}</div>
  {/if}
  <table>
    <thead><tr><th>Price</th><th>Bid size</th><th>Ask size</th><th>Price</th></tr></thead>
    <tbody>
      {#each asksReversed as [price, size]}
        <tr class="ask" class:best-ask={price === bestAsk}>
          <td></td><td></td>
          <td class="size"><span class="bar ask-bar" style="width: {100 * size / maxSize}%"></span>{formatSize(size)}</td>
          <td>{formatPrice(price)}</td>
        </tr>
      {/each}
      {#if bids.length && asks.length}
        <tr class="mid"><td colspan="4">—</td></tr>
      {/if}
      {#each bids as [price, size], i}
        <tr class="bid" class:best-bid={i === 0}>
          <td>{formatPrice(price)}</td>
          <td class="size"><span class="bar bid-bar" style="width: {100 * size / maxSize}%"></span>{formatSize(size)}</td>
          <td></td><td></td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .dom { padding: 4px; overflow: auto; }
  .summary { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; padding: 2px 6px; }
  table { width: 100%; border-collapse: collapse; font-size: 11px; }
  th, td { padding: 2px 6px; text-align: right; }
  .size { position: relative; min-width: 60px; }
  .bar { position: absolute; top: 0; right: 0; bottom: 0; max-width: 100%; border-radius: 1px; }
  .bid-bar { background: rgba(13, 148, 136, 0.35); }
  .ask-bar { background: rgba(185, 28, 28, 0.35); }
  .bid .size, .ask .size { color: var(--text); }
  .mid { color: #666; font-size: 10px; }
  .best-bid { background: rgba(13, 148, 136, 0.12); }
  .best-ask { background: rgba(185, 28, 28, 0.12); }
</style>
