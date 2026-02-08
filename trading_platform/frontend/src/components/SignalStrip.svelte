<script lang="ts">
  import { formatPrice } from '../lib/format'
  import type { MambaSignalData } from '../lib/api'

  export let lastPrice: number | null = null
  export let imbalance: { imbalance_pct: number } | null = null
  export let mambaSignal: MambaSignalData = null
  export let trendScores: Array<{ trend_power: number; trend_power_delta: number }> = []
  export let ruleSignals: Array<{ prob_reversal_rule: number }> = []

  $: latestTrend = trendScores[trendScores.length - 1]
  $: lastReversal = ruleSignals[ruleSignals.length - 1]
</script>

<div class="signal-strip">
  <div class="strip-item">
    <span class="label">Price</span>
    <span class="value num">{lastPrice != null ? formatPrice(lastPrice) : '—'}</span>
  </div>
  <div class="strip-item" class:positive={imbalance != null && imbalance.imbalance_pct > 0} class:negative={imbalance != null && imbalance.imbalance_pct < 0}>
    <span class="label">Imbalance</span>
    <span class="value num">{imbalance != null ? `${imbalance.imbalance_pct >= 0 ? '+' : ''}${imbalance.imbalance_pct.toFixed(1)}%` : '—'}</span>
  </div>
  <div class="strip-item" class:up={mambaSignal != null && mambaSignal.delta_score > 0} class:down={mambaSignal != null && mambaSignal.delta_score < 0}>
    <span class="label">Mamba</span>
    <span class="value num">
      {#if mambaSignal == null}
        —
      {:else}
        Up {(mambaSignal.prob_up * 100).toFixed(0)}% / Down {(mambaSignal.prob_down * 100).toFixed(0)}%
      {/if}
    </span>
  </div>
  <div class="strip-item" class:up={latestTrend != null && latestTrend.trend_power_delta > 0} class:down={latestTrend != null && latestTrend.trend_power_delta < 0}>
    <span class="label">Trend</span>
    <span class="value num">{latestTrend != null ? latestTrend.trend_power.toFixed(1) : '—'}</span>
  </div>
  <div class="strip-item">
    <span class="label">Reversal</span>
    <span class="value num">{lastReversal != null ? Math.round(lastReversal.prob_reversal_rule * 100) + '%' : '—'}</span>
  </div>
</div>

<style>
  .signal-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 20px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-panel-2);
    font-size: 11px;
    align-items: center;
  }
  .strip-item {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .strip-item .label {
    color: var(--text-muted);
  }
  .strip-item .value {
    font-variant-numeric: tabular-nums;
  }
  .strip-item.positive .value {
    color: var(--buy);
  }
  .strip-item.negative .value {
    color: var(--sell);
  }
  .strip-item.up .value {
    color: var(--buy);
  }
  .strip-item.down .value {
    color: var(--sell);
  }
  .num {
    font-variant-numeric: tabular-nums;
  }
</style>
