<script lang="ts">
  import { formatTime } from '../lib/format'
  import type { MambaSignalData } from '../lib/api'

  export let signal: MambaSignalData = null

  $: isUp = signal != null && signal.delta_score > 0
  $: isDown = signal != null && signal.delta_score < 0
</script>

<div class="mamba-signal">
  <div class="panel-title">Mamba</div>
  {#if signal == null}
    <div class="row empty">Нет данных (tick-anomaly)</div>
  {:else}
    <div class="row" class:up={isUp} class:down={isDown}>
      <span>Prob Up</span>
      <span class="num">{(signal.prob_up * 100).toFixed(1)}%</span>
    </div>
    <div class="row" class:up={isUp} class:down={isDown}>
      <span>Prob Down</span>
      <span class="num">{(signal.prob_down * 100).toFixed(1)}%</span>
    </div>
    <div class="row" class:up={isUp} class:down={isDown}>
      <span>Delta score</span>
      <span class="num">{signal.delta_score.toFixed(2)}</span>
    </div>
    <div class="row small">
      <span>Обновлено</span>
      <span>{signal.ts ? formatTime(signal.ts) : '—'}</span>
    </div>
  {/if}
</div>

<style>
  .mamba-signal {
    padding: 8px 0;
    border-top: 1px solid var(--border);
    margin-top: 8px;
    flex-shrink: 0;
  }
  .mamba-signal .panel-title {
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
  .row.empty {
    color: var(--text-muted);
    font-size: 10px;
  }
  .num {
    font-variant-numeric: tabular-nums;
  }
  .row.up span:last-child {
    color: var(--buy);
  }
  .row.down span:last-child {
    color: var(--sell);
  }
</style>
