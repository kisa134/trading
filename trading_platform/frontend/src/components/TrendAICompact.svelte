<script lang="ts">
  export let trendScores: Array<{ ts: number; trend_power: number; trend_power_delta: number }> = []
  export let exhaustionScores: Array<{ ts: number; exhaustion_score: number; absorption_score: number }> = []
  export let ruleSignals: Array<{ ts: number; prob_reversal_rule: number; reversal_horizon_bars: number; expected_move_range: [number, number] }> = []

  $: latestTrend = trendScores[trendScores.length - 1]
  $: latestExh = exhaustionScores[exhaustionScores.length - 1]
  $: lastSignal = ruleSignals[ruleSignals.length - 1]
</script>

<div class="trend-ai-compact">
  <div class="panel-title">Trend · сила тренда</div>
  <div class="row" class:up={latestTrend != null && latestTrend.trend_power_delta > 0} class:down={latestTrend != null && latestTrend.trend_power_delta < 0}>
    <span>TrendPower</span>
    <span>{latestTrend ? latestTrend.trend_power.toFixed(1) : '--'}</span>
  </div>
  <div class="row" class:up={latestTrend != null && latestTrend.trend_power_delta > 0} class:down={latestTrend != null && latestTrend.trend_power_delta < 0}>
    <span>ΔTrend</span>
    <span>{latestTrend ? latestTrend.trend_power_delta.toFixed(1) : '--'}</span>
  </div>
  <div class="row">
    <span>Exhaustion</span>
    <span>{latestExh ? latestExh.exhaustion_score.toFixed(0) : '--'}</span>
  </div>
  <div class="row">
    <span>Absorption</span>
    <span>{latestExh ? latestExh.absorption_score.toFixed(0) : '--'}</span>
  </div>
  <div class="row">
    <span>Reversal</span>
    <span>{lastSignal ? Math.round(lastSignal.prob_reversal_rule * 100) + '%' : '--'}</span>
  </div>
  {#if lastSignal}
    <div class="row small">
      <span>Range</span>
      <span>{lastSignal.expected_move_range[0]}–{lastSignal.expected_move_range[1]}</span>
    </div>
  {/if}
</div>

<style>
  .trend-ai-compact {
    padding: 8px 0;
    border-top: 1px solid var(--border);
    margin-top: 8px;
    flex-shrink: 0;
  }
  .trend-ai-compact .panel-title {
    margin-bottom: 6px;
    font-size: 11px;
    color: var(--text-muted);
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
</style>
