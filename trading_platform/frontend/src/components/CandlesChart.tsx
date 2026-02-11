import React, { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts'
import type { Candle, Trade, Liquidation } from '../lib/api'

interface CandlesChartProps {
  candles: Candle[]
  trades?: Trade[]
  liquidations?: Liquidation[]
}

const normalizeTs = (ts: number): number => {
  return ts < 10_000_000_000 ? ts * 1000 : ts
}

const convertToTradingViewTime = (timestamp: number): Time => {
  const normalized = normalizeTs(timestamp)
  // TradingView ожидает timestamp в секундах для типа 'time'
  return Math.floor(normalized / 1000) as Time
}

export const CandlesChart: React.FC<CandlesChartProps> = ({
  candles,
  trades = [],
  liquidations = [],
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 400 })

  // Инициализация графика
  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: dimensions.width,
      height: dimensions.height,
      layout: {
        background: { color: '#0a0a0a' },
        textColor: '#e0e0e0',
      },
      grid: {
        vertLines: { color: '#1a1a1a' },
        horzLines: { color: '#1a1a1a' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: '#333',
      },
      timeScale: {
        borderColor: '#333',
        timeVisible: true,
        secondsVisible: false,
      },
    })

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })

    chartRef.current = chart
    seriesRef.current = candlestickSeries

    // Обработка изменения размера
    const resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0) return
      const { width, height } = entries[0].contentRect
      setDimensions({ width, height })
      chart.applyOptions({ width, height })
    })

    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  // Обновление размеров графика
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.applyOptions({ width: dimensions.width, height: dimensions.height })
    }
  }, [dimensions])

  // Обновление данных свечей
  useEffect(() => {
    if (!seriesRef.current || candles.length === 0) return

    const data: CandlestickData[] = candles.map(candle => ({
      time: convertToTradingViewTime(candle.start),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
    }))

    seriesRef.current.setData(data)
  }, [candles])

  // Overlay сделок (опционально - можно добавить маркеры)
  // TradingView не поддерживает напрямую overlay точек, но можно использовать дополнительные серии

  return (
    <div
      ref={chartContainerRef}
      style={{
        width: '100%',
        height: '100%',
        minHeight: '400px',
      }}
    />
  )
}
