<script lang="ts">
  export let data: { ts: number; bids: [number, number][]; asks: [number, number][] } | null = null
  const limit = 20
  $: bids = data?.bids?.slice(0, limit) ?? []
  $: asks = data?.asks?.slice(0, limit) ?? []
  $: maxSize = Math.max(
    ...bids.map(([, s]) => s),
    ...asks.map(([, s]) => s),
    1
  )
</script>

<div class="dom">
  <table>
    <thead><tr><th>Price</th><th>Bid</th><th>Ask</th><th>Price</th></tr></thead>
    <tbody>
      {#each [...asks].reverse() as [price, size]}
        <tr class="ask">
          <td></td><td></td>
          <td class="size"><span class="bar ask-bar" style="width: {100 * size / maxSize}%"></span>{size.toFixed(2)}</td>
          <td>{price.toFixed(2)}</td>
        </tr>
      {/each}
      {#if bids.length && asks.length}
        <tr class="mid"><td colspan="4">—</td></tr>
      {/if}
      {#each bids as [price, size]}
        <tr class="bid">
          <td>{price.toFixed(2)}</td>
          <td class="size"><span class="bar bid-bar" style="width: {100 * size / maxSize}%"></span>{size.toFixed(2)}</td>
          <td></td><td></td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .dom { padding: 4px; overflow: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 11px; }
  th, td { padding: 2px 6px; text-align: right; }
  .size { position: relative; min-width: 60px; }
  .bar { position: absolute; top: 0; right: 0; bottom: 0; max-width: 100%; border-radius: 1px; }
  .bid-bar { background: rgba(13, 148, 136, 0.35); }
  .ask-bar { background: rgba(185, 28, 28, 0.35); }
  .bid .size, .ask .size { color: var(--text); }
  .mid { color: #666; font-size: 10px; }
</style>
