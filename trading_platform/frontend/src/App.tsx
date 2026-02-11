import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { OrderbookTable, type DOMData } from './components/OrderbookTable'
import { CandlesChart } from './components/CandlesChart'
import { TradesTable, type Trade } from './components/TradesTable'
import { MetricsPanel } from './components/MetricsPanel'
import { useWebSocket } from './hooks/useWebSocket'
import {
  fetchDom,
  fetchTrades,
  fetchKline,
  fetchOpenInterest,
  fetchLiquidations,
  fetchBybitSymbols,
  type Candle,
  type OpenInterestPoint,
  type Liquidation,
} from './lib/api'

type Exchange = 'bybit' | 'binance' | 'okx'

const CHANNELS = [
  'orderbook_realtime',
  'trades_realtime',
  'kline',
  'open_interest',
  'liquidations',
]

export const App: React.FC = () => {
  const [exchange, setExchange] = useState<Exchange>('bybit')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState(1)
  const [domDepth, setDomDepth] = useState(20)

  const [dom, setDom] = useState<DOMData | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [candles, setCandles] = useState<Candle[]>([])
  const [openInterest, setOpenInterest] = useState<OpenInterestPoint[]>([])
  const [liquidations, setLiquidations] = useState<Liquidation[]>([])

  const [symbols, setSymbols] = useState<string[]>([])
  const [symbolsLoading, setSymbolsLoading] = useState(false)
  const [symbolDropdownOpen, setSymbolDropdownOpen] = useState(false)
  const [symbolFilter, setSymbolFilter] = useState('')

  const lastPrice = useMemo(() => {
    if (trades.length > 0) {
      return trades[0].price
    }
    if (dom?.bids?.[0]?.[0] != null && dom?.asks?.[0]?.[0] != null) {
      return (dom.bids[0][0] + dom.asks[0][0]) / 2
    }
    return null
  }, [trades, dom])

  const symbolSearchResults = useMemo(() => {
    if (exchange !== 'bybit' || symbolFilter.length < 2) return []
    return symbols.filter(s => s.includes(symbolFilter.toUpperCase())).slice(0, 20)
  }, [symbols, symbolFilter, exchange])

  // Обработка WebSocket сообщений
  const handleWebSocketMessage = useCallback((message: any) => {
    if (message.type === 'dom' && message.data) {
      setDom(message.data)
      return
    }

    const stream = message.stream
    const data = message.data || message

    if (stream === 'orderbook_updates' || stream === 'orderbook_realtime') {
      if (data.bids && data.asks) {
        setDom({ ts: data.ts || 0, bids: data.bids, asks: data.asks })
      }
      return
    }

    if (stream === 'trades' || stream === 'trades_realtime') {
      setTrades(prev => [data, ...prev].slice(0, 200))
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
      setCandles(prev => {
        const idx = prev.findIndex(x => {
          const normalizeTs = (ts: number) => (ts < 10_000_000_000 ? ts * 1000 : ts)
          return normalizeTs(x.start) === normalizeTs(start)
        })
        if (idx >= 0) {
          const newCandles = [...prev]
          newCandles[idx] = c
          return newCandles
        } else {
          const newCandles = [...prev, c].sort((a, b) => {
            const normalizeTs = (ts: number) => (ts < 10_000_000_000 ? ts * 1000 : ts)
            return normalizeTs(a.start) - normalizeTs(b.start)
          })
          return newCandles.slice(-500)
        }
      })
      return
    }

    if (stream === 'open_interest' && data?.open_interest != null) {
      setOpenInterest(prev =>
        [
          ...prev,
          {
            ts: data.ts || 0,
            open_interest: Number(data.open_interest),
            open_interest_value: data.open_interest_value != null ? Number(data.open_interest_value) : undefined,
          },
        ].slice(-100)
      )
      return
    }

    if (stream === 'liquidations' && data?.price != null) {
      setLiquidations(prev =>
        [
          {
            ts: data.ts || 0,
            price: Number(data.price),
            quantity: Number(data.quantity ?? 0),
            side: String(data.side ?? ''),
          },
          ...prev,
        ].slice(0, 50)
      )
    }
  }, [])

  const { connected, connect, disconnect } = useWebSocket({
    exchange,
    symbol,
    channels: CHANNELS,
    onMessage: handleWebSocketMessage,
    autoConnect: true,
  })

  // Загрузка символов
  const loadSymbols = useCallback(async () => {
    if (exchange !== 'bybit') {
      setSymbols([])
      return
    }
    setSymbolsLoading(true)
    try {
      const syms = await fetchBybitSymbols()
      setSymbols(syms)
    } catch (err) {
      console.error('Failed to load symbols:', err)
      setSymbols([])
    } finally {
      setSymbolsLoading(false)
    }
  }, [exchange])

  // Загрузка начальных данных
  const loadInitialData = useCallback(async () => {
    try {
      const [domData, tradesData, candlesData, oiData, liqData] = await Promise.all([
        fetchDom(exchange, symbol),
        fetchTrades(exchange, symbol, 200),
        fetchKline(exchange, symbol, timeframe, 500),
        fetchOpenInterest(exchange, symbol, 100),
        fetchLiquidations(exchange, symbol, 50),
      ])
      setDom(domData)
      setTrades(tradesData)
      setCandles(candlesData)
      setOpenInterest(oiData)
      setLiquidations(liqData)
    } catch (err) {
      console.error('Failed to load initial data:', err)
    }
  }, [exchange, symbol, timeframe])

  // Обработка смены биржи
  const handleExchangeChange = useCallback(
    (newExchange: Exchange) => {
      setExchange(newExchange)
      setSymbol('BTCUSDT')
      setSymbolFilter('')
      setSymbolDropdownOpen(false)
    },
    []
  )

  // Обработка применения символа
  const applySymbol = useCallback((next: string) => {
    if (!next) return
    setSymbol(next.toUpperCase())
    setSymbolDropdownOpen(false)
    setSymbolFilter('')
  }, [])

  // Эффект для загрузки символов при смене биржи
  useEffect(() => {
    loadSymbols()
  }, [loadSymbols])

  // Эффект для загрузки данных при смене биржи/символа/таймфрейма
  useEffect(() => {
    loadInitialData()
  }, [loadInitialData])

  // Обработка клика вне dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node
      if (!document.querySelector('.symbol-combo')?.contains(target)) {
        setSymbolDropdownOpen(false)
      }
    }
    window.addEventListener('click', handleClickOutside)
    return () => window.removeEventListener('click', handleClickOutside)
  }, [])

  return (
    <div className="app">
      <div className="topbar">
        <div className="exchange-tabs">
          <button
            className={exchange === 'bybit' ? 'active' : ''}
            onClick={() => handleExchangeChange('bybit')}
          >
            Bybit
          </button>
          <button
            className={exchange === 'binance' ? 'active' : ''}
            onClick={() => handleExchangeChange('binance')}
          >
            Binance
          </button>
          <button
            className={exchange === 'okx' ? 'active' : ''}
            onClick={() => handleExchangeChange('okx')}
          >
            OKX
          </button>
        </div>

        <div className="symbol-selector">
          <div className="symbol-combo">
            <input
              type="text"
              value={symbol}
              onChange={e => {
                setSymbol(e.target.value.toUpperCase())
                setSymbolFilter(e.target.value.toUpperCase())
                if (exchange === 'bybit') {
                  setSymbolDropdownOpen(true)
                }
              }}
              onFocus={() => {
                if (exchange === 'bybit') {
                  setSymbolDropdownOpen(true)
                }
              }}
              placeholder="BTCUSDT"
            />
            {exchange === 'bybit' && symbolDropdownOpen && (
              <div className="symbol-dropdown">
                {symbolsLoading ? (
                  <div className="hint">Loading...</div>
                ) : symbolFilter.length < 2 ? (
                  <div className="hint">Type 2+ characters</div>
                ) : symbolSearchResults.length === 0 ? (
                  <div className="hint">No results</div>
                ) : (
                  symbolSearchResults.map(item => (
                    <button
                      key={item}
                      type="button"
                      className="result"
                      onClick={() => applySymbol(item)}
                    >
                      {item}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
          <button
            type="button"
            className="apply-btn"
            onClick={() => {
              setSymbolDropdownOpen(false)
              disconnect()
              connect()
              loadInitialData()
            }}
          >
            Apply
          </button>
        </div>

        <div className="controls">
          <label>
            Timeframe:
            <select
              value={timeframe}
              onChange={e => {
                setTimeframe(Number(e.target.value))
              }}
            >
              <option value={1}>1m</option>
              <option value={5}>5m</option>
              <option value={15}>15m</option>
              <option value={60}>1h</option>
            </select>
          </label>
          <label>
            DOM Depth:
            <select value={domDepth} onChange={e => setDomDepth(Number(e.target.value))}>
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
          </label>
          <div className={`status ${connected ? 'connected' : 'disconnected'}`}>
            <span className="dot"></span>
            <span>{connected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </div>

      <div className="main-layout">
        <div className="left-panel">
          <div className="panel-title">Orderbook · {symbol}</div>
          <OrderbookTable dom={dom} depth={domDepth} />
        </div>

        <div className="center-panel">
          <div className="panel-title">Chart · {symbol} · {timeframe}m</div>
          <CandlesChart candles={candles} trades={trades} liquidations={liquidations} />
        </div>

        <div className="right-panel">
          <MetricsPanel
            lastPrice={lastPrice}
            openInterest={openInterest}
            liquidations={liquidations}
          />
          <div className="panel-title" style={{ marginTop: '16px' }}>
            Trades · {symbol}
          </div>
          <TradesTable trades={trades} maxTrades={100} />
        </div>
      </div>
    </div>
  )
}
