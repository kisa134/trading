import React, { useMemo } from 'react'
import { formatPrice, formatSize } from '../lib/format'

export interface DOMData {
  ts: number
  bids: [number, number][]
  asks: [number, number][]
}

interface OrderbookTableProps {
  dom: DOMData | null
  depth?: number
}

interface OrderbookRow {
  price: number
  size: number
  total: number
}

export const OrderbookTable: React.FC<OrderbookTableProps> = ({ dom, depth = 20 }) => {
  const { bids, asks, maxTotal } = useMemo(() => {
    if (!dom) {
      return { bids: [], asks: [], maxTotal: 1 }
    }

    const bidsList = dom.bids.slice(0, depth)
    const asksList = dom.asks.slice(0, depth)

    const bidsWithTotal: OrderbookRow[] = bidsList.map((bid, i) => {
      const total = bidsList.slice(0, i + 1).reduce((sum, [, size]) => sum + size, 0)
      return { price: bid[0], size: bid[1], total }
    })

    const asksWithTotal: OrderbookRow[] = asksList.map((ask, i) => {
      const total = asksList.slice(0, i + 1).reduce((sum, [, size]) => sum + size, 0)
      return { price: ask[0], size: ask[1], total }
    })

    const maxTotal = Math.max(
      ...bidsWithTotal.map(b => b.total),
      ...asksWithTotal.map(a => a.total),
      1
    )

    return { bids: bidsWithTotal, asks: asksWithTotal, maxTotal }
  }, [dom, depth])

  const spread = useMemo(() => {
    if (bids.length === 0 || asks.length === 0) return null
    const spreadValue = asks[0].price - bids[0].price
    const spreadBps = (spreadValue / bids[0].price) * 10000
    return { value: spreadValue, bps: spreadBps }
  }, [bids, asks])

  return (
    <div className="orderbook">
      <div className="orderbook-header">
        <div className="header-col">Price</div>
        <div className="header-col">Size</div>
        <div className="header-col">Total</div>
      </div>
      <div className="orderbook-body">
        {/* Asks (top, red) */}
        <div className="asks">
          {asks.slice().reverse().map((ask, idx) => (
            <div
              key={`ask-${ask.price}-${idx}`}
              className="row ask"
              style={{ '--width': `${(ask.total / maxTotal) * 100}%` } as React.CSSProperties}
            >
              <div className="col price">{formatPrice(ask.price)}</div>
              <div className="col size">{formatSize(ask.size)}</div>
              <div className="col total">{formatSize(ask.total)}</div>
            </div>
          ))}
        </div>

        {/* Spread */}
        {spread && (
          <div className="spread">
            <div className="spread-label">Spread</div>
            <div className="spread-value">
              {formatPrice(spread.value)} ({spread.bps.toFixed(2)} bps)
            </div>
          </div>
        )}

        {/* Bids (bottom, green) */}
        <div className="bids">
          {bids.map((bid, idx) => (
            <div
              key={`bid-${bid.price}-${idx}`}
              className="row bid"
              style={{ '--width': `${(bid.total / maxTotal) * 100}%` } as React.CSSProperties}
            >
              <div className="col price">{formatPrice(bid.price)}</div>
              <div className="col size">{formatSize(bid.size)}</div>
              <div className="col total">{formatSize(bid.total)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
