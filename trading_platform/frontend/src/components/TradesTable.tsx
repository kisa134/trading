import React, { useMemo } from 'react'
import { formatTime, formatPrice, formatSize } from '../lib/format'

export interface Trade {
  side: string
  price: number
  size: number
  ts: number
  trade_id?: string
}

interface TradesTableProps {
  trades: Trade[]
  maxTrades?: number
  filterSide?: 'all' | 'buy' | 'sell'
}

export const TradesTable: React.FC<TradesTableProps> = ({
  trades,
  maxTrades = 100,
  filterSide = 'all',
}) => {
  const filteredTrades = useMemo(() => {
    return trades
      .filter(t => {
        if (filterSide === 'all') return true
        const side = (t.side || '').toLowerCase()
        if (filterSide === 'buy') return side === 'buy'
        return side === 'sell'
      })
      .slice(0, maxTrades)
  }, [trades, maxTrades, filterSide])

  return (
    <div className="trades">
      <div className="trades-header">
        <div className="header-col">Time</div>
        <div className="header-col">Price</div>
        <div className="header-col">Size</div>
        <div className="header-col">Side</div>
      </div>
      <div className="trades-body">
        {filteredTrades.length === 0 ? (
          <div className="empty">No trades</div>
        ) : (
          filteredTrades.map((trade, idx) => {
            const side = (trade.side || '').toLowerCase()
            const isBuy = side === 'buy'
            const isSell = side === 'sell'
            return (
              <div
                key={trade.trade_id || `trade-${trade.ts}-${idx}`}
                className={`row ${isBuy ? 'buy' : ''} ${isSell ? 'sell' : ''}`}
              >
                <div className="col time">{formatTime(trade.ts)}</div>
                <div className="col price">{formatPrice(trade.price)}</div>
                <div className="col size">{formatSize(trade.size)}</div>
                <div className="col side">{trade.side || '—'}</div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
