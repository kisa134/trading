import { useEffect, useRef, useState, useCallback } from 'react'

export interface WebSocketMessage {
  type?: string
  stream?: string
  data?: any
}

export interface UseWebSocketOptions {
  exchange: string
  symbol: string
  channels: string[]
  onMessage?: (message: WebSocketMessage) => void
  autoConnect?: boolean
}

export interface UseWebSocketReturn {
  connected: boolean
  connect: () => void
  disconnect: () => void
  send: (data: string) => void
}

export function useWebSocket({
  exchange,
  symbol,
  channels,
  onMessage,
  autoConnect = true,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const onMessageRef = useRef(onMessage)

  // Обновляем ref для onMessage, чтобы всегда использовать актуальную версию
  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    const isDev = typeof location !== 'undefined' && location.port === '5173'
    const envApi = (import.meta as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL ?? ''
    const derivedOnRender =
      typeof location !== 'undefined' && location.hostname.includes('onrender.com')
        ? location.protocol + '//' + location.hostname.replace(/trading-frontend/, 'trading-api')
        : ''
    const API_ORIGIN = envApi || derivedOnRender
    const API_WS = API_ORIGIN
      ? (API_ORIGIN.startsWith('https') ? 'wss:' : 'ws:') + '//' + new URL(API_ORIGIN).host + '/ws'
      : isDev
        ? `ws://${location.hostname}:8000/ws`
        : `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`

    const channelsStr = channels.join(',')
    const url = `${API_WS}?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(symbol)}&channels=${encodeURIComponent(channelsStr)}`

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        reconnectAttemptsRef.current = 0
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
      }

      ws.onclose = () => {
        setConnected(false)
        // Автоматическое переподключение с экспоненциальной задержкой
        if (autoConnect) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
          reconnectAttemptsRef.current++
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        }
      }

      ws.onerror = () => {
        setConnected(false)
      }

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          if (onMessageRef.current) {
            onMessageRef.current(message)
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
      setConnected(false)
    }
  }, [exchange, symbol, channels, autoConnect])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setConnected(false)
    reconnectAttemptsRef.current = 0
  }, [])

  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  const channelsKey = channels.join(',')

  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    return () => {
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exchange, symbol, channelsKey])

  return { connected, connect, disconnect, send }
}
