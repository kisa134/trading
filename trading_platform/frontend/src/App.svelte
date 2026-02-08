<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import DomAligned from './components/DomAligned.svelte'
  import Tape from './components/Tape.svelte'
  import Footprint from './components/Footprint.svelte'
  import Events from './components/Events.svelte'
  import TrendAI from './components/TrendAI.svelte'
  import ChartHeatmapBubbles from './components/ChartHeatmapBubbles.svelte'
  import { wsUrl, fetchBybitSymbols, fetchKline, fetchImbalance, uploadSnapshot, type Candle } from './lib/api'
  import { formatTime } from './lib/format'
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
  let domDepth = 20

  let activeTab: 'Flow' | 'Dashboard' | 'TrendAI' | 'Footprint' | 'MLLab' | 'Logs' | 'AI' = 'Flow'

  const channels = [
    'orderbook_realtime',
    'trades_realtime',
    'kline',
    'heatmap_stream',
    'footprint_stream',
    'events_stream',
    'scores',
    'exhaustion_absorption',
    'signals',
    'ai_response',
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
  let symbols: string[] = []
  let symbolsLoading = false
  let symbolsError = ''
  let symbolDropdownOpen = false
  let menuOpen = false

  let chartScale = { priceMin: 0, priceMax: 1, plotH: 300 }
  let bubbleMode: 'off' | 'candles' | 'trades' = 'candles'
  let imbalanceCurrent: { imbalance_pct: number } | null = null
  let chartHeatmapBubblesRef: import('./components/ChartHeatmapBubbles.svelte').default | null = null
  let snapshotIntervalId: ReturnType<typeof setInterval> | null = null
  const SNAPSHOT_INTERVAL_MS = 20000
  const LARGE_TRADE_MULT = 2.5
  let aiResponseText = ''
  let aiResponseTs = 0
  $: lastPrice =
    trades[0]?.price ??
    (dom?.bids?.[0]?.[0] != null && dom?.asks?.[0]?.[0] != null
      ? (dom.bids[0][0] + dom.asks[0][0]) / 2
      : null)

  function setDomDepthFromSelect(e: Event) {
    const el = e.currentTarget as HTMLSelectElement
    if (el) domDepth = Number(el.value)
  }

  function captureAndUploadSnapshot(trigger: 'timer' | 'volume_spike' | 'manual') {
    const canvas = chartHeatmapBubblesRef?.getHeatmapCanvas?.()
    if (!canvas || canvas.width === 0 || canvas.height === 0) return
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        const reader = new FileReader()
        reader.onloadend = () => {
          const base64 = (reader.result as string)?.split(',')[1]
          if (!base64) return
          uploadSnapshot({
            exchange,
            symbol,
            imageBase64: base64,
            ts: Date.now(),
            trigger,
          }).catch(() => {})
        }
        reader.readAsDataURL(blob)
      },
      'image/jpeg',
      0.85
    )
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
    ].filter(Boolean)
    const normalized = candidates.map((t: number) => normalizeTs(t))
    if (normalized.length) return Math.max(...normalized)
    return Date.now()
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
  const inWindow = (ts: number) => {
    const t = normalizeTs(ts)
    return t >= windowStart && t <= windowEnd
  }
  $: viewTrades = trades.filter(t => inWindow(t.ts)).slice(0, maxTrades)
  $: viewHeatmap = heatmapSlices.filter(s => inWindow(s.ts))
  $: viewFootprint = footprintBars.filter(b => inWindow(b.start))
  $: viewEvents = events.filter(e => inWindow(e.ts)).slice(0, maxEvents)

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
          const size = data?.size ?? data?.volume ?? 0
          if (size > 0 && trades.length >= 5) {
            const recent = trades.slice(0, 20).map((t: { size?: number }) => t.size ?? 0).filter(Boolean)
            const avg = recent.length ? recent.reduce((a: number, b: number) => a + b, 0) / recent.length : 0
            if (avg > 0 && size >= avg * LARGE_TRADE_MULT) captureAndUploadSnapshot('volume_spike')
          }
          return
        }
        if (stream === 'kline' && data?.start != null) {
          const start = data.start
          const c = {
            start,
            open: Number(data.open ?? 0),
            high: Number(data.high ?? 0),
            low: Number(data.low ?? 0),
            close: Number(data.close ?? 0),
            volume: Number(data.volume ?? 0),
            confirm: Boolean(data.confirm),
          }
          const idx = candles.findIndex((x) => normalizeTs(x.start) === normalizeTs(start))
          if (idx >= 0) candles[idx] = c
          else candles = [...candles, c].sort((a, b) => normalizeTs(a.start) - normalizeTs(b.start))
          candles = candles.slice(-500)
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
        if (stream === 'ai_response' && data?.text != null) {
          aiResponseText = data.text
          aiResponseTs = Date.now()
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

  async function loadImbalance() {
    try {
      const res = await fetchImbalance(exchange, symbol, 0)
      imbalanceCurrent = res?.current ? { imbalance_pct: res.current.imbalance_pct } : null
    } catch {
      imbalanceCurrent = null
    }
  }

  function handleExchangeChange() {
    isLive = true
    connect()
    loadSymbols()
    loadCandles()
    loadImbalance()
  }

  function applySymbol(next: string) {
    if (!next) return
    symbol = next.toUpperCase()
    symbolDropdownOpen = false
    isLive = true
    connect()
    loadCandles()
    loadImbalance()
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

  let imbalanceInterval: ReturnType<typeof setInterval> | null = null
  onMount(() => {
    connect()
    loadSymbols()
    loadCandles()
    loadImbalance()
    window.addEventListener('click', handleClickOutside)
    imbalanceInterval = setInterval(() => {
      if (activeTab === 'Flow') loadImbalance()
    }, 2000)
    snapshotIntervalId = setInterval(() => captureAndUploadSnapshot('timer'), SNAPSHOT_INTERVAL_MS)
  })
  onDestroy(() => {
    if (ws) ws.close()
    window.removeEventListener('click', handleClickOutside)
    if (imbalanceInterval) clearInterval(imbalanceInterval)
    if (snapshotIntervalId) clearInterval(snapshotIntervalId)
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
  <button class:active={activeTab === 'AI'} on:click={() => (activeTab = 'AI')}>AI</button>
  <button class:active={activeTab === 'Logs'} on:click={() => (activeTab = 'Logs')}>Logs</button>
</div>

{#if activeTab === 'Flow'}
  <div class="layout layout-unified">
    <aside class="left panel panel-left-unified" style="width: 240px;">
      <div class="panel-title">Events · {symbol}</div>
      <div class="events-wrap"><Events items={viewEvents} /></div>
      <div class="panel-title" style="margin-top: 8px;">Tape · {symbol}</div>
      <div class="tape-wrap"><Tape trades={viewTrades} /></div>
      <div class="panel-title" style="margin-top: 8px;">Footprint</div>
      <div class="footprint-wrap"><Footprint bars={viewFootprint} /></div>
    </aside>
    <main class="center panel center-unified">
      <div class="panel-title chart-title-row">
        <span>Heatmap + Volume · {symbol} · {timeframe} · {isLive ? 'Live' : 'Paused'}</span>
        <button type="button" class="ai-snapshot-btn-inline" on:click={() => captureAndUploadSnapshot('manual')} title="Отправить снимок ИИ">Снимок для ИИ</button>
        <span class="imbalance-indicator" class:positive={imbalanceCurrent != null && imbalanceCurrent.imbalance_pct > 0} class:negative={imbalanceCurrent != null && imbalanceCurrent.imbalance_pct < 0}>
          {imbalanceCurrent != null ? `Imbalance: ${imbalanceCurrent.imbalance_pct >= 0 ? '+' : ''}${imbalanceCurrent.imbalance_pct.toFixed(1)}%` : 'Imbalance: —'}
        </span>
        <select class="bubble-mode-select" bind:value={bubbleMode} title="Пузырьки">
          <option value="off">Пузырьки: выкл</option>
          <option value="candles">По свечам</option>
          <option value="trades">По сделкам</option>
        </select>
      </div>
      <ChartHeatmapBubbles
        bind:this={chartHeatmapBubblesRef}
        slices={viewHeatmap}
        candles={candles}
        trades={viewTrades}
        {bubbleMode}
        {windowStart}
        {windowEnd}
        onTimeWindowChange={setTimeWindow}
        onScaleChange={(info) => {
          chartScale = { priceMin: info.priceMin, priceMax: info.priceMax, plotH: info.plotH }
        }}
      />
    </main>
    <aside class="right panel panel-right-unified" style="width: 220px;">
      <div class="panel-title dom-title">
        <span>DOM · {symbol}</span>
        <select class="depth-select" value={domDepth} on:change={setDomDepthFromSelect}>
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </div>
      <DomAligned
        data={dom}
        priceMin={chartScale.priceMin}
        priceMax={chartScale.priceMax}
        plotH={chartScale.plotH}
        lastPrice={lastPrice}
        depth={domDepth}
        width={200}
      />
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
{:else if activeTab === 'AI'}
  <div class="layout single">
    <div class="panel ai-panel" style="flex: 1; padding: 12px; display: flex; flex-direction: column;">
      <div class="panel-title">AI · {symbol}</div>
      <p class="ai-hint">Ответы приходят после каждого снимка. Ручной снимок: вкладка Flow → кнопка «Снимок для ИИ».</p>
      <button type="button" class="ai-snapshot-btn" on:click={() => captureAndUploadSnapshot('manual')}>Сделать снимок сейчас</button>
      <div class="ai-response-box">
        {#if aiResponseTs > 0}
          <div class="ai-meta">Обновлено: {formatTime(aiResponseTs)}</div>
          <div class="ai-text">{aiResponseText}</div>
        {:else}
          <div class="placeholder">Ожидание ответа ИИ… Подключитесь и откройте Flow для отправки снимков.</div>
        {/if}
      </div>
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
  .layout-unified { align-items: stretch; }
  .left { flex: 0 0 auto; border-right: none; overflow: auto; min-width: 120px; }
  .panel-left-unified { display: flex; flex-direction: column; overflow-y: auto; }
  .panel-left-unified .panel-title { flex-shrink: 0; }
  .panel-left-unified .events-wrap { max-height: 180px; overflow-y: auto; min-height: 0; }
  .panel-left-unified .tape-wrap { max-height: 220px; overflow-y: auto; min-height: 0; }
  .panel-left-unified .footprint-wrap { max-height: 200px; overflow-y: auto; min-height: 0; }
  .resizer { width: 6px; flex-shrink: 0; cursor: col-resize; background: var(--border); }
  .resizer:hover { background: var(--accent); }
  .dom-title { display: flex; justify-content: space-between; align-items: center; }
  .chart-title-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
  .bubble-mode-select { padding: 2px 6px; font-size: 11px; background: #020202; border: 1px solid var(--border-strong); color: var(--text); }
  .imbalance-indicator { font-size: 11px; font-variant-numeric: tabular-nums; }
  .imbalance-indicator.positive { color: var(--buy); }
  .imbalance-indicator.negative { color: var(--sell); }
  .depth-select { padding: 2px 4px; font-size: 10px; background: #020202; border: 1px solid var(--border-strong); color: var(--text); }
  .center { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
  .center-unified { display: flex; flex-direction: column; min-height: 0; }
  .center-unified :global(.wrap) { flex: 1; min-height: 200px; }
  .panel-right-unified { display: flex; flex-direction: column; overflow: hidden; }
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
  .ai-panel .ai-hint { color: var(--text-muted); font-size: 12px; margin: 0 0 8px 0; }
  .ai-snapshot-btn { margin-bottom: 12px; align-self: flex-start; }
  .ai-snapshot-btn-inline { margin-left: 8px; font-size: 11px; padding: 2px 8px; }
  .ai-response-box { flex: 1; min-height: 120px; border: 1px solid var(--border); background: #080808; padding: 12px; border-radius: 4px; overflow-y: auto; }
  .ai-meta { font-size: 10px; color: var(--text-muted); margin-bottom: 8px; }
  .ai-text { white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.5; }
</style>
