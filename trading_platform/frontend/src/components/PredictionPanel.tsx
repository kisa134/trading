import React, { useMemo } from 'react'
import { formatPrice, formatTime } from '../lib/format'
import type { Prediction } from '../lib/api'

interface PredictionPanelProps {
  prediction: Prediction | null
}

export const PredictionPanel: React.FC<PredictionPanelProps> = ({ prediction }) => {
  const directionDisplay = useMemo(() => {
    if (!prediction || !prediction.direction) return null
    
    const isLong = prediction.direction === 'long'
    const confidence = prediction.confidence || 0
    
    return {
      direction: isLong ? 'LONG' : 'SHORT',
      confidence,
      color: isLong ? '#10b981' : '#ef4444',
      bgColor: isLong ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
    }
  }, [prediction])

  if (!prediction || !prediction.direction) {
    return (
      <div className="prediction-panel">
        <div className="prediction-header">Mamba Prediction</div>
        <div className="prediction-empty">No prediction available</div>
      </div>
    )
  }

  return (
    <div className="prediction-panel">
      <div className="prediction-header">Mamba Prediction</div>
      
      <div
        className="prediction-direction"
        style={{
          backgroundColor: directionDisplay?.bgColor,
          borderColor: directionDisplay?.color,
        }}
      >
        <div className="direction-label">{directionDisplay?.direction}</div>
        <div className="confidence-value">
          {(directionDisplay?.confidence || 0) * 100}%
        </div>
      </div>

      <div className="prediction-details">
        <div className="detail-row">
          <span className="detail-label">Long Prob:</span>
          <span className="detail-value">{((prediction.long_prob || 0) * 100).toFixed(1)}%</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Short Prob:</span>
          <span className="detail-value">{((prediction.short_prob || 0) * 100).toFixed(1)}%</span>
        </div>
      </div>

      {prediction.current_price != null && (
        <div className="prediction-price">
          <div className="price-row">
            <span className="price-label">Current:</span>
            <span className="price-value">{formatPrice(prediction.current_price)}</span>
          </div>
          {prediction.predicted_price != null && (
            <>
              <div className="price-row">
                <span className="price-label">Predicted:</span>
                <span
                  className="price-value"
                  style={{
                    color:
                      prediction.price_change_pct > 0
                        ? '#10b981'
                        : prediction.price_change_pct < 0
                          ? '#ef4444'
                          : '#888',
                  }}
                >
                  {formatPrice(prediction.predicted_price)}
                </span>
              </div>
              <div className="price-change">
                {prediction.price_change_pct > 0 ? '+' : ''}
                {prediction.price_change_pct.toFixed(2)}%
              </div>
            </>
          )}
        </div>
      )}

      <div className="prediction-time">
        {formatTime(prediction.ts)}
      </div>
    </div>
  )
}
