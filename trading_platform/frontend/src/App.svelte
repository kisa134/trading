<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import Dom from './components/Dom.svelte'
  import Tape from './components/Tape.svelte'
  import Heatmap from './components/Heatmap.svelte'
  import Footprint from './components/Footprint.svelte'
  import Events from './components/Events.svelte'
  import TrendAI from './components/TrendAI.svelte'
  import { wsUrl, fetchBybitSymbols, fetchKline, type Candle } from './lib/api'
  import { formatTime } from './lib/format'
  import Chart from './components/Chart.svelte'
  import Dashboard from './components/Dashboard.svelte'

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
  let candles: Candle[] = []
  let chartMode: 'line' | 'candles' = 'candles'
  let chartColorUp = '#22d3ee'
  let chartColorDown = '#fb7185'
  let chartLineColor = '#38bdf8'
  let domWidth = 220
  let domDepth = 20
  let resizingDom = false

  let activeTab: 'Flow' | 'Dashboard' | 'TrendAI' | 'Footprint' | 'MLLab' | 'Logs' = 'Flow'

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
  let isLive = true
  let manualWindowStart = 0
  let manualWindowEnd = 0
  const panelColors = ['#38bdf8', '#a855f7', '#f59e0b', '#22d3ee', '#fb7185']
  type ChartPanel = { id: string; timeframe: string; color: string; windowStart: number; windowEnd: number }
  let chartPanels: ChartPanel[] = []
  let addPanelTf = '5m'
  let addPanelColor = '#a855f7'

  let symbols: string[] = []
  let symbolsLoading = false
  let symbolsError = ''
  let symbolDropdownOpen = false
  let menuOpen = false

  function setDomDepthFromSelect(e: Event) {
    const el = e.currentTarget as HTMLSelectElement
    if (el) domDepth = Number(el.value)
  }

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
  $: windowStart = isLive ? currentLatest - timeframeMs : manualWindowStart
  $: windowEnd = isLive ? currentLatest : manualWindowEnd
  function setTimeWindow(start: number, end: number) {
    isLive = false
    manualWindowStart = start
    manualWindowEnd = end
  }
  function goLive() {
    isLive = true
  }
  function addChartPanel() {
    const ms = timeframeOptions.find((t) => t.label === addPanelTf)?.ms ?? 300_000
    const now = currentLatest
    chartPanels = [
      ...chartPanels,
      { id: crypto.randomUUID(), timeframe: addPanelTf, color: addPanelColor, windowStart: now - ms, windowEnd: now },
    ]
  }
  function removeChartPanel(id: string) {
    chartPanels = chartPanels.filter((p) => p.id !== id)
  }
  function setPanelTimeWindow(id: string, start: number, end: number) {
    chartPanels = chartPanels.map((p) => (p.id === id ? { ...p, windowStart: start, windowEnd: end } : p))
  }
  function panelGoLive(id: string) {
    const p = chartPanels.find((x) => x.id === id)
    if (!p) return
    const ms = timeframeOptions.find((t) => t.label === p.timeframe)?.ms ?? 300_000
    chartPanels = chartPanels.map((x) =>
      x.id === id ? { ...x, windowEnd: currentLatest, windowStart: currentLatest - ms } : x
    )
  }
  const inWindow = (ts: number) => {
    const t = normalizeTs(ts)
    return t >= windowStart && t <= windowEnd
  }
  $: viewTrades = trades.filter(t => inWindow(t.ts)).slice(0, maxTrades)
  $: viewHeatmap = heatmapSlices.filter(s => inWindow(s.ts))
  $: viewFootprint = footprintBars.filter(b => inWindow(b.start))
  $: viewEvents = events.filter(e => inWindow(e.ts)).slice(0, maxEvents)
  function heatmapForWindow(start: number, end: number) {
    return heatmapSlices.filter((s) => {
      const t = normalizeTs(s.ts)
      return t >= start && t <= end
    })
  }

  $: symbolFilter = (symbol || '').trim().toUpperCase()
  $: symbolSearchResults = exchange === 'bybit' && symbolFilter.length >= 2
    ? symbols.filter(s => s.includes(symbolFilter)).slice(0, 20)
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

  async function loadCandles() {
    try {
      candles = await fetchKline(exchange, symbol, 1, 500)
    } catch {
      candles = []
    }
  }

  function handleExchangeChange() {
    isLive = true
    connect()
    loadSymbols()
    loadCandles()
  }

  function applySymbol(next: string) {
    if (!next) return
    symbol = next.toUpperCase()
    symbolDropdownOpen = false
    isLive = true
    connect()
    loadCandles()
  }

  function onSymbolKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      if (symbolSearchResults.length) applySymbol(symbolSearchResults[0])
      else connect()
    }
  }


  function handleClickOutside(e: MouseEvent) {
    const t = e.target as Node
    if (!document.querySelector('.symbol-combo')?.contains(t)) symbolDropdownOpen = false
    if (!document.querySelector('.status-menu-wrap')?.contains(t)) menuOpen = false
  }

  function handleDomResizeStart() {
    resizingDom = true
  }
  function handleDomResizeMove(e: MouseEvent) {
    if (!resizingDom) return
    const newW = e.clientX
    if (newW >= 160 && newW <= 500) domWidth = newW
  }
  function handleDomResizeEnd() {
    resizingDom = false
  }

  onMount(() => {
    connect()
    loadSymbols()
    loadCandles()
    window.addEventListener('click', handleClickOutside)
    window.addEventListener('mousemove', handleDomResizeMove)
    window.addEventListener('mouseup', handleDomResizeEnd)
  })
  onDestroy(() => {
    if (ws) ws.close()
    window.removeEventListener('click', handleClickOutside)
    window.removeEventListener('mousemove', handleDomResizeMove)
    window.removeEventListener('mouseup', handleDomResizeEnd)
  })
</script>

<div class="topbar">
  <div class="panel market-row">
    <div class="market-one-line">
      <label for="exchange-select" class="sr-only">Exchange</label>
      <select id="exchange-select" bind:value={exchange} on:change={handleExchangeChange}>
        <option value="bybit">Bybit</option>
        <option value="binance">Binance</option>
        <option value="okx">OKX</option>
      </select>
      <div class="symbol-combo">
        <label for="symbol-input" class="sr-only">Symbol</label>
        <input
          id="symbol-input"
          type="text"
          bind:value={symbol}
          placeholder="BTCUSDT"
          on:focus={() => { if (exchange === 'bybit') symbolDropdownOpen = true }}
          on:keydown={onSymbolKeydown}
          on:input={() => { if (exchange === 'bybit' && symbolFilter.length >= 2) symbolDropdownOpen = true }}
        />
        {#if exchange === 'bybit' && symbolDropdownOpen}
          <div class="symbol-dropdown">
            {#if symbolsLoading}
              <div class="hint">Загрузка...</div>
            {:else if symbolsError}
              <div class="hint error">{symbolsError}</div>
            {:else if symbolFilter.length < 2}
              <div class="hint">Введите 2+ символа</div>
            {:else if symbolSearchResults.length === 0}
              <div class="hint">Ничего не найдено</div>
            {:else}
              {#each symbolSearchResults as item}
                <button type="button" class="result" on:click={() => applySymbol(item)}>{item}</button>
              {/each}
            {/if}
          </div>
        {/if}
      </div>
      <button type="button" class="apply-btn" on:click={() => { symbolDropdownOpen = false; connect() }}>Apply</button>
    </div>
  </div>
  <div class="panel control-panel timeframe-panel">
    <div class="panel-title">Timeframe</div>
    <div class="chip-row">
      {#each timeframeOptions as tf}
        <button
          type="button"
          class:active={timeframe === tf.label}
          on:click={() => { timeframe = tf.label; isLive = true }}
        >
          {tf.label}
        </button>
      {/each}
    </div>
    <div class="hint">Окно: {timeframe}{#if !isLive} · пауза{/if}</div>
  </div>
  <div class="panel status-compact">
    <div class="status-menu-wrap">
      <span class="dot" class:ok={connected} class:disconnected={!connected}></span>
      <span class="status-text">{connected ? 'Connected' : 'Disconnected'}</span>
      <button type="button" class="menu-btn" title="Меню" on:click={() => (menuOpen = !menuOpen)} aria-expanded={menuOpen}>⋮</button>
      {#if menuOpen}
        <div class="menu-dropdown" role="menu">
          <div class="menu-item static">Обновлено: {formatTime(currentLatest)}</div>
          <button type="button" class="menu-item" on:click={() => { goLive(); menuOpen = false }}>В реалтайм</button>
          <button type="button" class="menu-item" on:click={() => { connect(); menuOpen = false }}>Reconnect</button>
          <button type="button" class="menu-item" on:click={() => (menuOpen = false)}>Закрыть</button>
        </div>
      {/if}
    </div>
  </div>
</div>

<div class="tabs">
  <button class:active={activeTab === 'Flow'} on:click={() => (activeTab = 'Flow')}>Flow</button>
  <button class:active={activeTab === 'Dashboard'} on:click={() => (activeTab = 'Dashboard')}>Dashboard</button>
  <button class:active={activeTab === 'TrendAI'} on:click={() => (activeTab = 'TrendAI')}>Trend AI</button>
  <button class:active={activeTab === 'Footprint'} on:click={() => (activeTab = 'Footprint')}>Footprint</button>
  <button class:active={activeTab === 'MLLab'} on:click={() => (activeTab = 'MLLab')}>ML Lab</button>
  <button class:active={activeTab === 'Logs'} on:click={() => (activeTab = 'Logs')}>Logs</button>
</div>

{#if activeTab === 'Flow'}
  <div class="layout" class:resizing={resizingDom}>
    <aside class="left panel" style="width: {domWidth}px;">
      <div class="panel-title dom-title">
        <span>DOM · {symbol}</span>
        <select class="depth-select" value={domDepth} on:change={setDomDepthFromSelect}>
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </div>
      <Dom data={dom} depth={domDepth} />
    </aside>
    <div
      class="resizer"
      role="separator"
      aria-label="Resize DOM panel"
      on:mousedown={(e) => { e.preventDefault(); handleDomResizeStart() }}
    ></div>
    <main class="center">
      <div class="panel chart-panel">
        <div class="panel-title chart-title">
          <span>Price · {symbol}</span>
          <div class="chart-controls">
            <button type="button" class:active={chartMode === 'line'} on:click={() => (chartMode = 'line')}>Line</button>
            <button type="button" class:active={chartMode === 'candles'} on:click={() => (chartMode = 'candles')}>Candles</button>
            <label class="color-label">Up <input type="color" bind:value={chartColorUp} /></label>
            <label class="color-label">Down <input type="color" bind:value={chartColorDown} /></label>
            <label class="color-label">Line <input type="color" bind:value={chartLineColor} /></label>
          </div>
        </div>
        <Chart
          candles={candles}
          {windowStart}
          {windowEnd}
          onTimeWindowChange={setTimeWindow}
          mode={chartMode}
          lineColor={chartLineColor}
          candleUp={chartColorUp}
          candleDown={chartColorDown}
        />
      </div>
      <div class="panel" style="flex: 1; display: flex; flex-direction: column;">
        <div class="panel-title">Heatmap · {symbol} · {timeframe} · {isLive ? 'Live' : 'Paused'}</div>
        <Heatmap
          slices={viewHeatmap}
          {windowStart}
          {windowEnd}
          onTimeWindowChange={setTimeWindow}
        />
      </div>
      <div class="add-panel-row panel">
        <span class="add-panel-label">Добавить панель:</span>
        <select bind:value={addPanelTf}>
          {#each timeframeOptions as tf}
            <option value={tf.label}>{tf.label}</option>
          {/each}
        </select>
        <label class="color-label">Цвет <input type="color" bind:value={addPanelColor} /></label>
        <button type="button" on:click={addChartPanel}>+ Панель</button>
      </div>
      <div class="multi-panels">
        {#each chartPanels as panel}
          <div class="panel heatmap-panel" style="border-left: 4px solid {panel.color};">
            <div class="panel-title heatmap-panel-title">
              <span>{panel.timeframe}</span>
              <div class="panel-actions">
                <button type="button" class="small" on:click={() => panelGoLive(panel.id)}>Live</button>
                <button type="button" class="small" on:click={() => removeChartPanel(panel.id)}>×</button>
              </div>
            </div>
            <Heatmap
              slices={heatmapForWindow(panel.windowStart, panel.windowEnd)}
              windowStart={panel.windowStart}
              windowEnd={panel.windowEnd}
              onTimeWindowChange={(s, e) => setPanelTimeWindow(panel.id, s, e)}
            />
          </div>
        {/each}
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
{:else if activeTab === 'Dashboard'}
  <Dashboard
    {symbol}
    {dom}
    trades={viewTrades}
    heatmapSlices={heatmapSlices}
    footprintBars={footprintBars}
    events={viewEvents}
    {candles}
    {windowStart}
    {windowEnd}
    setTimeWindow={setTimeWindow}
    trendScores={trendScores}
    exhaustionScores={exhaustionScores}
    ruleSignals={ruleSignals}
  />
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
    grid-template-columns: 1fr auto auto;
    gap: 8px;
    padding: 8px;
    border-bottom: 1px solid var(--border);
    background: #050505;
    align-items: start;
  }
  .market-row { padding: 6px 10px; }
  .market-one-line {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .market-one-line select {
    padding: 4px 8px;
    background: #020202;
    border: 1px solid var(--border-strong);
    color: var(--text);
    font-family: inherit;
    min-width: 90px;
  }
  .symbol-combo { position: relative; min-width: 140px; }
  .symbol-combo input {
    padding: 4px 8px;
    width: 100%;
    background: #020202;
    border: 1px solid var(--border-strong);
    color: var(--text);
    font-family: inherit;
  }
  .symbol-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin-top: 2px;
    background: var(--bg-panel);
    border: 1px solid var(--border-strong);
    max-height: 200px;
    overflow-y: auto;
    z-index: 100;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
  }
  .symbol-dropdown .result {
    padding: 4px 8px;
    border: 1px solid var(--border);
    background: #060606;
    color: var(--text);
    text-align: left;
  }
  .symbol-dropdown .result:hover { border-color: var(--accent); color: var(--accent); }
  .apply-btn { padding: 4px 12px; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); }
  .control-panel { padding: 6px; display: flex; flex-direction: column; gap: 6px; min-height: 72px; }
  .timeframe-panel { min-height: 72px; }
  .chip-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .nav-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .chip-row button {
    padding: 4px 8px;
    border: 1px solid var(--border-strong);
    background: transparent;
    color: var(--text);
  }
  .chip-row button.active { background: linear-gradient(90deg, rgba(56, 189, 248, 0.25), rgba(168, 85, 247, 0.25)); }
  .result {
    padding: 4px 6px;
    border: 1px solid var(--border);
    background: #060606;
    color: var(--text);
    text-align: left;
  }
  .result:hover { border-color: var(--accent); color: var(--accent); }
  .hint { color: var(--text-muted); padding: 4px; }
  .hint.error { color: var(--sell); }
  .time-range { color: var(--text-muted); font-variant-numeric: tabular-nums; font-size: 11px; }
  .status-compact { padding: 6px 10px; }
  .status-menu-wrap { position: relative; display: flex; align-items: center; gap: 6px; }
  .status-text { font-size: 11px; color: var(--text-muted); }
  .menu-btn {
    padding: 2px 6px;
    font-size: 14px;
    line-height: 1;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    cursor: pointer;
  }
  .menu-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 4px;
    background: var(--bg-panel);
    border: 1px solid var(--border-strong);
    min-width: 160px;
    z-index: 100;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  .menu-item {
    display: block;
    width: 100%;
    padding: 6px 10px;
    text-align: left;
    background: none;
    border: none;
    color: var(--text);
    font-size: 12px;
    cursor: pointer;
  }
  .menu-item.static { color: var(--text-muted); cursor: default; }
  .menu-item:hover:not(.static) { background: #111; }

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
  .layout.resizing { user-select: none; }
  .layout.single { padding: 8px; }
  .left { flex: 0 0 auto; border-right: none; overflow: auto; min-width: 120px; }
  .resizer { width: 6px; flex-shrink: 0; cursor: col-resize; background: var(--border); }
  .resizer:hover { background: var(--accent); }
  .dom-title { display: flex; justify-content: space-between; align-items: center; }
  .depth-select { padding: 2px 4px; font-size: 10px; background: #020202; border: 1px solid var(--border-strong); color: var(--text); }
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
  .chart-panel { flex: 0 0 180px; min-height: 140px; display: flex; flex-direction: column; }
  .chart-title { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; }
  .chart-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .chart-controls button { padding: 2px 8px; font-size: 11px; }
  .chart-controls .color-label { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-muted); }
  .chart-controls .color-label input[type="color"] { width: 20px; height: 16px; padding: 0; border: 1px solid var(--border); cursor: pointer; }
  .add-panel-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; flex-wrap: wrap; }
  .add-panel-label { color: var(--text-muted); font-size: 11px; }
  .add-panel-row select { padding: 4px 8px; background: #020202; border: 1px solid var(--border-strong); color: var(--text); }
  .multi-panels { display: flex; flex-wrap: wrap; gap: 8px; }
  .heatmap-panel { flex: 1 1 280px; min-width: 200px; min-height: 160px; display: flex; flex-direction: column; }
  .heatmap-panel-title { display: flex; justify-content: space-between; align-items: center; }
  .panel-actions { display: flex; gap: 4px; }
  .panel-actions .small { padding: 2px 6px; font-size: 10px; }
</style>
