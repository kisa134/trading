<script lang="ts">
  import MambaSignal from './MambaSignal.svelte'
  import type { MambaSignalData } from '../lib/api'

  export let mambaSignal: MambaSignalData = null
  export let trendScores: Array<{ ts: number; trend_power: number; trend_power_delta: number }> = []
  export let exhaustionScores: Array<{ ts: number; exhaustion_score: number; absorption_score: number }> = []
  export let ruleSignals: Array<{ ts: number; prob_reversal_rule: number; reversal_horizon_bars: number; expected_move_range: [number, number] }> = []

  $: latestTrend = trendScores[trendScores.length - 1]
  $: latestExh = exhaustionScores[exhaustionScores.length - 1]
  $: lastSignal = ruleSignals[ruleSignals.length - 1]
</script>

<div class="mllab-dashboard">
  <section class="mllab-card">
    <div class="panel-title">Mamba Signal</div>
    <MambaSignal signal={mambaSignal} />
  </section>
  <section class="mllab-card">
    <div class="panel-title">Trend</div>
    <div class="row" class:up={latestTrend != null && latestTrend.trend_power_delta > 0} class:down={latestTrend != null && latestTrend.trend_power_delta < 0}>
      <span>TrendPower</span>
      <span class="num">{latestTrend != null ? latestTrend.trend_power.toFixed(1) : '—'}</span>
    </div>
    <div class="row" class:up={latestTrend != null && latestTrend.trend_power_delta > 0} class:down={latestTrend != null && latestTrend.trend_power_delta < 0}>
      <span>ΔTrend</span>
      <span class="num">{latestTrend != null ? latestTrend.trend_power_delta.toFixed(1) : '—'}</span>
    </div>
  </section>
  <section class="mllab-card">
    <div class="panel-title">Exhaustion / Absorption</div>
    <div class="row">
      <span>Exhaustion</span>
      <span class="num">{latestExh != null ? latestExh.exhaustion_score.toFixed(0) : '—'}</span>
    </div>
    <div class="row">
      <span>Absorption</span>
      <span class="num">{latestExh != null ? latestExh.absorption_score.toFixed(0) : '—'}</span>
    </div>
  </section>
  <section class="mllab-card">
    <div class="panel-title">Rule Reversal</div>
    <div class="row">
      <span>Reversal prob</span>
      <span class="num">{lastSignal != null ? Math.round(lastSignal.prob_reversal_rule * 100) + '%' : '—'}</span>
    </div>
    {#if lastSignal}
      <div class="row small">
        <span>Horizon (bars)</span>
        <span>{lastSignal.reversal_horizon_bars}</span>
      </div>
      <div class="row small">
        <span>Expected range</span>
        <span>{lastSignal.expected_move_range[0]} – {lastSignal.expected_move_range[1]}</span>
      </div>
    {/if}
  </section>
</div>

<style>
  .mllab-dashboard {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
    padding: 12px;
  }
  .mllab-card {
    border: 1px solid var(--border);
    background: var(--bg-panel);
    border-radius: 4px;
    padding: 10px;
  }
  .mllab-card .panel-title {
    margin-bottom: 8px;
    font-size: 11px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border);
    padding-bottom: 4px;
  }
  .mllab-card .mamba-signal {
    border-top: none;
    margin-top: 0;
    padding-top: 0;
  }
  .mllab-card .mamba-signal .panel-title {
    display: none;
  }
  .row {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
    font-size: 11px;
  }
  .row.small {
    font-size: 10px;
    color: var(--text-muted);
  }
  .row.up span:last-child {
    color: var(--buy);
  }
  .row.down span:last-child {
    color: var(--sell);
  }
  .num {
    font-variant-numeric: tabular-nums;
  }
</style>
