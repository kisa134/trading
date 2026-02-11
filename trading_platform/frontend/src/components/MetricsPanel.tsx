import React, { useMemo } from 'react'
import { formatPrice, formatTime } from '../lib/format'
import type { OpenInterestPoint, Liquidation } from '../lib/api'

interface MetricsPanelProps {
  lastPrice: number | null
  openInterest: OpenInterestPoint[]
  liquidations: Liquidation[]
  maxLiquidations?: number
}

export const MetricsPanel: React.FC<MetricsPanelProps> = ({
  lastPrice,
  openInterest,
  liquidations,
  maxLiquidations = 10,
}) => {
  const currentOI = useMemo(() => {
    return openInterest.length > 0 ? openInterest[openInterest.length - 1] : null
  }, [openInterest])

  const oiChange = useMemo(() => {
    if (openInterest.length >= 2) {
      return openInterest[openInterest.length - 1].open_interest - openInterest[openInterest.length - 2].open_interest
    }
    return 0
  }, [openInterest])

  const recentLiquidations = useMemo(() => {
    return liquidations.slice(0, maxLiquidations)
  }, [liquidations, maxLiquidations])

  return (
    <div className="metrics">
      <div className="metric-section">
        <div className="section-title">Last Price</div>
        <div className="price-value">{lastPrice != null ? formatPrice(lastPrice) : '—'}</div>
      </div>

      <div className="metric-section">
        <div className="section-title">Open Interest</div>
        {currentOI ? (
          <>
            <div className="oi-value">{formatPrice(currentOI.open_interest, 0)}</div>
            <div className={`oi-change ${oiChange > 0 ? 'positive' : oiChange < 0 ? 'negative' : ''}`}>
              {oiChange > 0 ? '+' : ''}{formatPrice(oiChange, 0)}
            </div>
            {currentOI.open_interest_value != null && (
              <div className="oi-value-usd">${formatPrice(currentOI.open_interest_value, 0)}</div>
            )}
          </>
        ) : (
          <div className="empty">—</div>
        )}
      </div>

      <div className="metric-section">
        <div className="section-title">Liquidations</div>
        <div className="liquidations-list">
          {recentLiquidations.length === 0 ? (
            <div className="empty">No liquidations</div>
          ) : (
            recentLiquidations.map((liq, idx) => {
              const side = (liq.side || '').toLowerCase()
              const isBuy = side === 'buy'
              const isSell = side === 'sell'
              return (
                <div
                  key={`liq-${liq.ts}-${idx}`}
                  className={`liq-item ${isBuy ? 'buy' : ''} ${isSell ? 'sell' : ''}`}
                >
                  <div className="liq-price">{formatPrice(liq.price)}</div>
                  <div className="liq-qty">{formatPrice(liq.quantity, 2)}</div>
                  <div className="liq-side">{liq.side}</div>
                  <div className="liq-time">{formatTime(liq.ts)}</div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
