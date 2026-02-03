<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import Dom from './components/Dom.svelte'
  import Tape from './components/Tape.svelte'
  import Heatmap from './components/Heatmap.svelte'
  import Footprint from './components/Footprint.svelte'
  import Events from './components/Events.svelte'
  import TrendAI from './components/TrendAI.svelte'
  import { wsUrl, fetchBybitSymbols } from './lib/api'

  let exchange = 'bybit'
  let symbol = 'BTCUSDT'
  let connected = false
  let ws: WebSocket | null = null

  let dom: { ts: number; bids: [number, number][]; asks: [number, number][] } | null = null
  let trades: Array<{ side: string; price: number; size: number; ts: number }> = []
  let heatmapSlices: Array<{ ts: number; rows: Array<{ price: number; vol_bid: number; vol_ask: number }> }> = []
  let footprintBars: Array<{ start: number; end: number; levels: Array<{ price: number; vol_bid: number; vol_ask: number; delta: number }> }> = []
  let events: Array<{ type: string; ts: number; [k: string]: unknown }> = []
  let trendScores: Array<{ ts: number; trend_power: number; trend_power_delta: number }> = []
  let exhaustionScores: Array<{ ts: number; exhaustion_score: number; absorption_score: number }> = []
  let ruleSignals: Array<{ ts: number; prob_reversal_rule: number; reversal_horizon_bars: number; expected_move_range: [number, number] }> = []

  let activeTab: 'Flow' | 'TrendAI' | 'Footprint' | 'MLLab' | 'Logs' = 'Flow'

  const channels = [
    'orderbook_realtime',
    'trades_realtime',
    'heatmap_stream',
    'footprint_stream',
    'events_stream',
    'scores',
    'exhaustion_absorption',
    'signals',
  ]
  const maxTrades = 200
  const maxHeatmap = 150
  const maxFootprint = 50
  const maxEvents = 100

  const timeframeOptions = [
    { label: '1m', ms: 60_000 },
    { label: '5m', ms: 5 * 60_000 },
    { label: '15m', ms: 15 * 60_000 },
    { label: '1h', ms: 60 * 60_000 },
    { label: '4h', ms: 4 * 60 * 60_000 },
  ]
  let timeframe = '5m'
  let timeShift = 0
  let timeAnchor: number | null = null

  let symbols: string[] = []
  let symbolsLoading = false
  let symbolsError = ''
  let searchQuery = ''

  const normalizeTs = (ts: number) => (ts < 10_000_000_000 ? ts * 1000 : ts)

  $: timeframeMs = timeframeOptions.find(t => t.label === timeframe)?.ms ?? 300_000
  $: currentLatest = (() => {
    const lastHeatmap = heatmapSlices[heatmapSlices.length - 1]?.ts
    const lastFootprint = footprintBars[footprintBars.length - 1]
    const lastTrade = trades[0]?.ts
    const lastEvent = events[0]?.ts
    const candidates = [
      lastHeatmap,
      lastFootprint?.end ?? lastFootprint?.start,
      lastTrade,
      lastEvent,
      Date.now(),
    ]
    const normalized = candidates.filter(Boolean).map((t: number) => normalizeTs(t))
    return normalized.length ? Math.max(...normalized) : Date.now()
  })()
  $: effectiveLatest = timeShift === 0 ? currentLatest : (timeAnchor ?? currentLatest)
  $: if (timeShift === 0) timeAnchor = null
  $: windowEnd = effectiveLatest - timeShift * timeframeMs
  $: windowStart = windowEnd - timeframeMs
  const inWindow = (ts: number) => {
    const t = normalizeTs(ts)
    return t >= windowStart && t <= windowEnd
  }
  $: viewTrades = trades.filter(t => inWindow(t.ts)).slice(0, maxTrades)
  $: viewHeatmap = heatmapSlices.filter(s => inWindow(s.ts))
  $: viewFootprint = footprintBars.filter(b => inWindow(b.start))
  $: viewEvents = events.filter(e => inWindow(e.ts)).slice(0, maxEvents)

  $: searchUpper = searchQuery.trim().toUpperCase()
  $: searchResults = exchange === 'bybit' && searchUpper.length >= 2
    ? symbols.filter(s => s.includes(searchUpper)).slice(0, 20)
    : []

  function connect() {
    if (ws) try { ws.close() } catch (_) {}
    const url = wsUrl(exchange, symbol, channels)
    ws = new WebSocket(url)
    ws.onopen = () => { connected = true }
    ws.onclose = () => { connected = false }
    ws.onerror = () => { connected = false }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'dom' && msg.data) {
          dom = msg.data
          return
        }
        const stream = msg.stream
        const data = msg.data || msg
        if (stream === 'orderbook_updates' || stream === 'orderbook_realtime') {
          if (data.bids && data.asks) dom = { ts: data.ts || 0, bids: data.bids, asks: data.asks }
          return
        }
        if (stream === 'trades' || stream === 'trades_realtime') {
          trades = [data, ...trades].slice(0, maxTrades)
          return
        }
        if (stream === 'heatmap_slices' || stream === 'heatmap_stream') {
          heatmapSlices = [...heatmapSlices, data].slice(-maxHeatmap)
          return
        }
        if (stream === 'footprint_bars' || stream === 'footprint_stream') {
          footprintBars = [...footprintBars, data].slice(-maxFootprint)
          return
        }
        if (stream === 'events' || stream === 'events_stream') {
          events = [{ ...data, ts: data.ts || Date.now() }, ...events].slice(0, maxEvents)
          return
        }
        if (stream === 'scores.trend') {
          trendScores = [...trendScores, data].slice(-200)
          return
        }
        if (stream === 'scores.exhaustion') {
          exhaustionScores = [...exhaustionScores, data].slice(-200)
          return
        }
        if (stream === 'signals.rule_reversal') {
          ruleSignals = [...ruleSignals, data].slice(-200)
        }
      } catch (_) {}
    }
  }

  async function loadSymbols() {
    if (exchange !== 'bybit') {
      symbols = []
      symbolsError = ''
      return
    }
    symbolsLoading = true
    symbolsError = ''
    try {
      symbols = await fetchBybitSymbols()
    } catch (err) {
      symbolsError = 'Не удалось загрузить список инструментов Bybit.'
      symbols = []
    } finally {
      symbolsLoading = false
    }
  }

  function handleExchangeChange() {
    timeShift = 0
    connect()
    loadSymbols()
  }

  function applySymbol(next: string) {
    if (!next) return
    symbol = next.toUpperCase()
    searchQuery = ''
    timeShift = 0
    connect()
  }

  function onSearchKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && searchResults.length) applySymbol(searchResults[0])
  }

  function shiftBack() {
    if (timeShift === 0) timeAnchor = currentLatest
    timeShift = Math.min(timeShift + 1, 500)
  }

  function shiftForward() {
    timeShift = Math.max(timeShift - 1, 0)
    if (timeShift === 0) timeAnchor = null
  }

  function resetTime() {
    timeShift = 0
    timeAnchor = null
  }

  onMount(() => {
    connect()
    loadSymbols()
  })
  onDestroy(() => { if (ws) ws.close() })
</script>

<div class="topbar">
  <div class="panel control-panel">
    <div class="panel-title">Market</div>
    <div class="control-row">
      <label for="exchange-select">Exchange</label>
      <select id="exchange-select" bind:value={exchange} on:change={handleExchangeChange}>
        <option value="bybit">Bybit</option>
        <option value="binance">Binance</option>
        <option value="okx">OKX</option>
      </select>
    </div>
    <div class="control-row">
      <label for="symbol-input">Symbol</label>
      <input id="symbol-input" type="text" bind:value={symbol} placeholder="BTCUSDT" on:keydown={(e) => e.key === 'Enter' && connect()} />
      <button type="button" class="ghost" on:click={() => connect()}>Apply</button>
    </div>
    <div class="control-row">
      <label for="search-input">Поиск (Bybit)</label>
      <input
        id="search-input"
        type="text"
        bind:value={searchQuery}
        placeholder="ETHUSDT, SOLUSDT, DOGEUSDT..."
        disabled={exchange !== 'bybit'}
        on:keydown={onSearchKeydown}
      />
    </div>
    <div class="search-results">
      {#if exchange !== 'bybit'}
        <div class="hint">Поиск доступен только для Bybit.</div>
      {:else if symbolsLoading}
        <div class="hint">Загружаю список инструментов...</div>
      {:else if symbolsError}
        <div class="hint error">{symbolsError}</div>
      {:else if searchUpper.length < 2}
        <div class="hint">Введите минимум 2 символа для поиска.</div>
      {:else if searchResults.length === 0}
        <div class="hint">Ничего не найдено.</div>
      {:else}
        <div class="result-list">
          {#each searchResults as item}
            <button type="button" class="result" on:click={() => applySymbol(item)}>{item}</button>
          {/each}
        </div>
      {/if}
    </div>
  </div>
  <div class="panel control-panel">
    <div class="panel-title">Timeframe</div>
    <div class="chip-row">
      {#each timeframeOptions as tf}
        <button
          type="button"
          class:active={timeframe === tf.label}
          on:click={() => { timeframe = tf.label; timeShift = 0 }}
        >
          {tf.label}
        </button>
      {/each}
    </div>
    <div class="hint">Окно: {timeframe} · шаг истории: {timeShift}</div>
  </div>
  <div class="panel control-panel">
    <div class="panel-title">Time Navigator</div>
    <div class="nav-row">
      <button type="button" on:click={shiftBack}>◀ Назад</button>
      <button type="button" on:click={shiftForward} disabled={timeShift === 0}>Вперёд ▶</button>
      <button type="button" on:click={resetTime}>В реалтайм</button>
    </div>
    <div class="time-range">
      {new Date(windowStart).toLocaleTimeString()} — {new Date(windowEnd).toLocaleTimeString()}
    </div>
  </div>
  <div class="panel control-panel">
    <div class="panel-title">Status</div>
    <div class="status-line">
      <span class="dot" class:ok={connected} class:disconnected={!connected}></span>
      <span>{connected ? 'Connected' : 'Disconnected'}</span>
    </div>
    <button type="button" on:click={() => connect()}>Reconnect</button>
  </div>
</div>

<div class="tabs">
  <button class:active={activeTab === 'Flow'} on:click={() => (activeTab = 'Flow')}>Flow</button>
  <button class:active={activeTab === 'TrendAI'} on:click={() => (activeTab = 'TrendAI')}>Trend AI</button>
  <button class:active={activeTab === 'Footprint'} on:click={() => (activeTab = 'Footprint')}>Footprint</button>
  <button class:active={activeTab === 'MLLab'} on:click={() => (activeTab = 'MLLab')}>ML Lab</button>
  <button class:active={activeTab === 'Logs'} on:click={() => (activeTab = 'Logs')}>Logs</button>
</div>

{#if activeTab === 'Flow'}
  <div class="layout">
    <aside class="left panel" style="width: 220px;">
      <div class="panel-title">DOM · {symbol}</div>
      <Dom data={dom} />
    </aside>
    <main class="center">
      <div class="panel" style="flex: 1; display: flex; flex-direction: column;">
        <div class="panel-title">Heatmap · {symbol} · {timeframe}</div>
        <Heatmap slices={viewHeatmap} />
      </div>
      <div class="panel footprint-row">
        <div class="panel-title">Footprint</div>
        <Footprint bars={viewFootprint} />
      </div>
    </main>
    <aside class="right panel" style="width: 260px;">
      <div class="panel-title">Tape · {symbol}</div>
      <Tape trades={viewTrades} />
      <div class="panel-title" style="margin-top: 8px;">Events</div>
      <Events items={viewEvents} />
    </aside>
  </div>
{:else if activeTab === 'TrendAI'}
  <div class="layout single">
    <TrendAI {trendScores} {exhaustionScores} {ruleSignals} />
  </div>
{:else if activeTab === 'Footprint'}
  <div class="layout single">
    <div class="panel" style="flex: 1;">
      <div class="panel-title">Footprint · {symbol}</div>
      <Footprint bars={footprintBars} />
    </div>
  </div>
{:else if activeTab === 'MLLab'}
  <div class="layout single">
    <div class="panel" style="flex: 1; padding: 12px;">
      <div class="panel-title">ML Lab</div>
      <div class="placeholder">Mamba и метрики будут добавлены в v2.</div>
    </div>
  </div>
{:else if activeTab === 'Logs'}
  <div class="layout single">
    <div class="panel" style="flex: 1; padding: 12px;">
      <div class="panel-title">Logs</div>
      <div class="placeholder">Системные логи сервисов будут добавлены в v2.</div>
    </div>
  </div>
{/if}

<style>
  .topbar {
    display: grid;
    grid-template-columns: 2fr 1.2fr 1.4fr 0.8fr;
    gap: 8px;
    padding: 8px;
    border-bottom: 1px solid var(--border);
    background: #050505;
  }
  .control-panel { padding: 6px; display: flex; flex-direction: column; gap: 6px; min-height: 160px; }
  .control-row { display: grid; grid-template-columns: 90px 1fr auto; gap: 6px; align-items: center; }
  .control-row label { color: var(--text-muted); }
  .control-row input, .control-row select {
    padding: 4px 6px;
    background: #020202;
    border: 1px solid var(--border-strong);
    color: var(--text);
    font-family: inherit;
  }
  .control-row input:disabled { color: #666; }
  .chip-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .nav-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .chip-row button {
    padding: 4px 8px;
    border: 1px solid var(--border-strong);
    background: transparent;
    color: var(--text);
  }
  .chip-row button.active { background: linear-gradient(90deg, rgba(56, 189, 248, 0.25), rgba(168, 85, 247, 0.25)); }
  .search-results { min-height: 60px; }
  .result-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px; }
  .result {
    padding: 4px 6px;
    border: 1px solid var(--border);
    background: #060606;
    color: var(--text);
    text-align: left;
  }
  .result:hover { border-color: var(--accent); color: var(--accent); }
  .hint { color: var(--text-muted); }
  .hint.error { color: var(--sell); }
  .time-range { color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .status-line { display: flex; align-items: center; gap: 8px; }

  .tabs {
    display: flex;
    gap: 6px;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-panel);
  }
  .tabs button {
    padding: 4px 10px;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    cursor: pointer;
  }
  .tabs button.active { background: #101010; border-color: var(--border-strong); }
  .layout { display: flex; flex: 1; min-height: 0; }
  .layout.single { padding: 8px; }
  .left { border-right: 1px solid var(--border); overflow: auto; }
  .center { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
  .footprint-row { flex: 0 0 140px; min-height: 120px; overflow: auto; }
  .right { border-left: 1px solid var(--border); overflow: auto; display: flex; flex-direction: column; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #666; }
  .dot.ok { background: var(--buy); }
  .dot.disconnected { background: #666; }
  button {
    padding: 4px 10px;
    cursor: pointer;
    background: #040404;
    border: 1px solid var(--border);
    color: var(--text);
    font-family: inherit;
  }
  button:disabled { opacity: 0.6; cursor: not-allowed; }
  button.ghost { background: transparent; }
  .placeholder { color: #777; padding: 8px; }
</style>
