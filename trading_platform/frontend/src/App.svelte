<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import OrderbookTable from './components/OrderbookTable.svelte'
  import CandlesChart from './components/CandlesChart.svelte'
  import TradesTable from './components/TradesTable.svelte'
  import MetricsPanel from './components/MetricsPanel.svelte'
  import { wsUrl, fetchDom, fetchTrades, fetchKline, fetchOpenInterest, fetchLiquidations, fetchBybitSymbols, type Candle, type OpenInterestPoint, type Liquidation } from './lib/api'
  import { formatPrice } from './lib/format'

  let exchange: 'bybit' | 'binance' | 'okx' = 'bybit'
  let symbol = 'BTCUSDT'
  let connected = false
  let ws: WebSocket | null = null

  let dom: { ts: number; bids: [number, number][]; asks: [number, number][] } | null = null
  let trades: Array<{ side: string; price: number; size: number; ts: number; trade_id?: string }> = []
  let candles: Candle[] = []
  let openInterest: OpenInterestPoint[] = []
  let liquidations: Liquidation[] = []
  let domDepth = 20
  let timeframe = 1 // minutes
  let maxTrades = 100

  let symbols: string[] = []
  let symbolsLoading = false
  let symbolDropdownOpen = false

  $: lastPrice = trades[0]?.price ?? (dom?.bids?.[0]?.[0] != null && dom?.asks?.[0]?.[0] != null ? (dom.bids[0][0] + dom.asks[0][0]) / 2 : null)

  const channels = [
    'orderbook_realtime',
    'trades_realtime',
    'kline',
    'open_interest',
    'liquidations',
  ]

  function connect() {
    if (ws) {
      try {
        ws.close()
      } catch (_) {}
    }
    const url = wsUrl(exchange, symbol, channels)
    ws = new WebSocket(url)
    ws.onopen = () => {
      connected = true
    }
    ws.onclose = () => {
      connected = false
    }
    ws.onerror = () => {
      connected = false
    }
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
          if (data.bids && data.asks) {
            dom = { ts: data.ts || 0, bids: data.bids, asks: data.asks }
          }
          return
        }

        if (stream === 'trades' || stream === 'trades_realtime') {
          trades = [data, ...trades].slice(0, maxTrades)
          return
        }

        if (stream === 'kline' && data?.start != null) {
          const start = data.start
          const c: Candle = {
            start,
            open: Number(data.open ?? 0),
            high: Number(data.high ?? 0),
            low: Number(data.low ?? 0),
            close: Number(data.close ?? 0),
            volume: Number(data.volume ?? 0),
            confirm: Boolean(data.confirm),
          }
          const idx = candles.findIndex((x) => x.start === start)
          if (idx >= 0) {
            candles[idx] = c
          } else {
            candles = [...candles, c].sort((a, b) => a.start - b.start)
          }
          candles = candles.slice(-500)
          return
        }

        if (stream === 'open_interest' && data?.open_interest != null) {
          openInterest = [...openInterest, {
            ts: data.ts || 0,
            open_interest: Number(data.open_interest),
            open_interest_value: data.open_interest_value != null ? Number(data.open_interest_value) : undefined,
          }].slice(-100)
          return
        }

        if (stream === 'liquidations' && data?.price != null) {
          liquidations = [{
            ts: data.ts || 0,
            price: Number(data.price),
            quantity: Number(data.quantity ?? 0),
            side: String(data.side ?? ''),
          }, ...liquidations].slice(0, 50)
        }
      } catch (_) {}
    }
  }

  async function loadSymbols() {
    if (exchange !== 'bybit') {
      symbols = []
      return
    }
    symbolsLoading = true
    try {
      symbols = await fetchBybitSymbols()
    } catch (err) {
      symbols = []
    } finally {
      symbolsLoading = false
    }
  }

  async function loadInitialData() {
    try {
      dom = await fetchDom(exchange, symbol)
      trades = await fetchTrades(exchange, symbol, maxTrades)
      candles = await fetchKline(exchange, symbol, timeframe, 500)
      openInterest = await fetchOpenInterest(exchange, symbol, 100)
      liquidations = await fetchLiquidations(exchange, symbol, 50)
    } catch (err) {
      console.error('Failed to load initial data:', err)
    }
  }

  function handleExchangeChange() {
    connect()
    loadSymbols()
    loadInitialData()
  }

  function applySymbol(next: string) {
    if (!next) return
    symbol = next.toUpperCase()
    symbolDropdownOpen = false
    connect()
    loadInitialData()
  }

  function handleClickOutside(e: MouseEvent) {
    const t = e.target as Node
    if (!document.querySelector('.symbol-combo')?.contains(t)) {
      symbolDropdownOpen = false
    }
  }

  onMount(() => {
    connect()
    loadSymbols()
    loadInitialData()
    window.addEventListener('click', handleClickOutside)
  })

  onDestroy(() => {
    if (ws) ws.close()
    window.removeEventListener('click', handleClickOutside)
  })

  $: symbolFilter = (symbol || '').trim().toUpperCase()
  $: symbolSearchResults = exchange === 'bybit' && symbolFilter.length >= 2
    ? symbols.filter(s => s.includes(symbolFilter)).slice(0, 20)
    : []
</script>

<div class="app">
  <div class="topbar">
    <div class="exchange-tabs">
      <button
        class:active={exchange === 'bybit'}
        on:click={() => { exchange = 'bybit'; handleExchangeChange() }}
      >
        Bybit
      </button>
      <button
        class:active={exchange === 'binance'}
        on:click={() => { exchange = 'binance'; handleExchangeChange() }}
      >
        Binance
      </button>
      <button
        class:active={exchange === 'okx'}
        on:click={() => { exchange = 'okx'; handleExchangeChange() }}
      >
        OKX
      </button>
    </div>

    <div class="symbol-selector">
      <div class="symbol-combo">
        <input
          type="text"
          bind:value={symbol}
          placeholder="BTCUSDT"
          on:focus={() => { if (exchange === 'bybit') symbolDropdownOpen = true }}
          on:input={() => { if (exchange === 'bybit' && symbolFilter.length >= 2) symbolDropdownOpen = true }}
        />
        {#if exchange === 'bybit' && symbolDropdownOpen}
          <div class="symbol-dropdown">
            {#if symbolsLoading}
              <div class="hint">Loading...</div>
            {:else if symbolFilter.length < 2}
              <div class="hint">Type 2+ characters</div>
            {:else if symbolSearchResults.length === 0}
              <div class="hint">No results</div>
            {:else}
              {#each symbolSearchResults as item}
                <button type="button" class="result" on:click={() => applySymbol(item)}>{item}</button>
              {/each}
            {/if}
          </div>
        {/if}
      </div>
      <button type="button" class="apply-btn" on:click={() => { symbolDropdownOpen = false; connect(); loadInitialData() }}>
        Apply
      </button>
    </div>

    <div class="controls">
      <label>
        Timeframe:
        <select bind:value={timeframe} on:change={() => loadInitialData()}>
          <option value={1}>1m</option>
          <option value={5}>5m</option>
          <option value={15}>15m</option>
          <option value={60}>1h</option>
        </select>
      </label>
      <label>
        DOM Depth:
        <select bind:value={domDepth}>
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </label>
      <div class="status" class:connected={connected} class:disconnected={!connected}>
        <span class="dot"></span>
        <span>{connected ? 'Connected' : 'Disconnected'}</span>
      </div>
    </div>
  </div>

  <div class="main-layout">
    <div class="left-panel">
      <div class="panel-title">Orderbook · {symbol}</div>
      <OrderbookTable {dom} {domDepth} />
    </div>

    <div class="center-panel">
      <div class="panel-title">Chart · {symbol} · {timeframe}m</div>
      <CandlesChart {candles} {trades} width={800} height={400} />
    </div>

    <div class="right-panel">
      <MetricsPanel {lastPrice} {openInterest} {liquidations} />
      <div class="panel-title" style="margin-top: 16px;">Trades · {symbol}</div>
      <TradesTable {trades} {maxTrades} />
    </div>
  </div>
</div>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #050505;
    color: #e0e0e0;
  }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  .topbar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    background: #0a0a0a;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }

  .exchange-tabs {
    display: flex;
    gap: 4px;
  }

  .exchange-tabs button {
    padding: 6px 16px;
    background: transparent;
    border: 1px solid #333;
    color: #888;
    cursor: pointer;
    font-size: 13px;
  }

  .exchange-tabs button.active {
    background: #1a1a1a;
    border-color: #555;
    color: #e0e0e0;
  }

  .symbol-selector {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .symbol-combo {
    position: relative;
  }

  .symbol-combo input {
    padding: 6px 12px;
    background: #0a0a0a;
    border: 1px solid #333;
    color: #e0e0e0;
    font-size: 13px;
    width: 120px;
  }

  .symbol-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin-top: 2px;
    background: #0a0a0a;
    border: 1px solid #333;
    max-height: 200px;
    overflow-y: auto;
    z-index: 100;
    display: flex;
    flex-direction: column;
  }

  .symbol-dropdown .result {
    padding: 6px 12px;
    border: none;
    background: transparent;
    color: #e0e0e0;
    text-align: left;
    cursor: pointer;
  }

  .symbol-dropdown .result:hover {
    background: #1a1a1a;
  }

  .apply-btn {
    padding: 6px 16px;
    background: #1a1a1a;
    border: 1px solid #333;
    color: #e0e0e0;
    cursor: pointer;
    font-size: 13px;
  }

  .controls {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-left: auto;
  }

  .controls label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #888;
  }

  .controls select {
    padding: 4px 8px;
    background: #0a0a0a;
    border: 1px solid #333;
    color: #e0e0e0;
    font-size: 12px;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
  }

  .status .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #666;
  }

  .status.connected .dot {
    background: #10b981;
  }

  .main-layout {
    display: grid;
    grid-template-columns: 280px 1fr 320px;
    flex: 1;
    overflow: hidden;
    gap: 1px;
    background: #333;
  }

  .left-panel,
  .center-panel,
  .right-panel {
    background: #0a0a0a;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .panel-title {
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #888;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }

  .hint {
    padding: 8px 12px;
    color: #888;
    font-size: 11px;
  }
</style>
