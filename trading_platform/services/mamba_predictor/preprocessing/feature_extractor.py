"""
Feature extraction from market data (trades, orderbook, kline, OI, liquidations).
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import deque


class MarketFeatureExtractor:
    """
    Извлечение признаков из различных источников рыночных данных.
    Объединяет все источники в единый вектор признаков для Mamba модели.
    """
    
    def __init__(self, orderbook_depth: int = 20):
        self.orderbook_depth = orderbook_depth
    
    def extract_from_trades(
        self,
        trades: List[Dict],
        window_sec: int = 60
    ) -> np.ndarray:
        """
        Извлечение признаков из сделок.
        
        Returns:
            Массив признаков: [price, size, buy_volume, sell_volume, delta, aggression, trade_rate]
        """
        if not trades:
            return np.zeros(7)
        
        # Последняя сделка
        last_trade = trades[-1]
        price = float(last_trade.get("price", 0))
        size = float(last_trade.get("size", 0))
        side = str(last_trade.get("side", "")).lower()
        
        # Агрегация за окно
        buy_volume = sum(
            float(t.get("size", 0))
            for t in trades
            if str(t.get("side", "")).lower().startswith("b")
        )
        sell_volume = sum(
            float(t.get("size", 0))
            for t in trades
            if not str(t.get("side", "")).lower().startswith("b")
        )
        total_volume = buy_volume + sell_volume
        
        # Delta (разница между buy и sell объемом)
        delta = (buy_volume - sell_volume) / max(total_volume, 1e-10)
        
        # Aggression (отношение размера к среднему)
        avg_size = np.mean([float(t.get("size", 0)) for t in trades]) if trades else size
        aggression = size / max(avg_size, 1e-10)
        
        # Trade rate (количество сделок в секунду)
        if len(trades) >= 2:
            time_span = (trades[-1].get("ts", 0) - trades[0].get("ts", 0)) / 1000.0
            trade_rate = len(trades) / max(time_span, 1.0)
        else:
            trade_rate = 0.0
        
        return np.array([price, size, buy_volume, sell_volume, delta, aggression, trade_rate])
    
    def extract_from_orderbook(
        self,
        orderbook: Dict
    ) -> np.ndarray:
        """
        Извлечение признаков из стакана заявок.
        
        Returns:
            Массив признаков: [spread, volume_imbalance, bid_depth, ask_depth, weighted_mid]
        """
        if not orderbook or "bids" not in orderbook or "asks" not in orderbook:
            return np.zeros(5)
        
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        if not bids or not asks:
            return np.zeros(5)
        
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        
        # Spread
        spread = best_ask - best_bid
        spread_pct = spread / max(best_bid, 1e-10)
        
        # Volume imbalance
        bid_volume = sum(float(b[1]) for b in bids[:self.orderbook_depth])
        ask_volume = sum(float(a[1]) for a in asks[:self.orderbook_depth])
        total_depth = bid_volume + ask_volume
        volume_imbalance = (bid_volume - ask_volume) / max(total_depth, 1e-10)
        
        # Depth (общая глубина)
        bid_depth = len(bids)
        ask_depth = len(asks)
        
        # Weighted mid price
        if bid_volume > 0 and ask_volume > 0:
            weighted_mid = (best_bid * bid_volume + best_ask * ask_volume) / (bid_volume + ask_volume)
        else:
            weighted_mid = (best_bid + best_ask) / 2
        
        return np.array([spread_pct, volume_imbalance, bid_depth, ask_depth, weighted_mid])
    
    def extract_from_kline(
        self,
        klines: List[Dict],
        use_indicators: bool = True
    ) -> np.ndarray:
        """
        Извлечение признаков из свечей (OHLCV).
        
        Returns:
            Массив признаков: [open, high, low, close, volume, rsi, macd, ...]
        """
        if not klines:
            return np.zeros(8 if use_indicators else 5)
        
        last_candle = klines[-1]
        open_price = float(last_candle.get("open", 0))
        high = float(last_candle.get("high", 0))
        low = float(last_candle.get("low", 0))
        close = float(last_candle.get("close", 0))
        volume = float(last_candle.get("volume", 0))
        
        features = [open_price, high, low, close, volume]
        
        if use_indicators and len(klines) >= 14:
            # RSI (упрощенный)
            rsi = self._calculate_rsi(klines)
            features.append(rsi)
            
            # MACD (упрощенный)
            macd = self._calculate_macd(klines)
            features.append(macd)
            
            # Price change
            if len(klines) >= 2:
                prev_close = float(klines[-2].get("close", close))
                price_change = (close - prev_close) / max(prev_close, 1e-10)
                features.append(price_change)
            else:
                features.append(0.0)
        else:
            if use_indicators:
                features.extend([0.0, 0.0, 0.0])
        
        return np.array(features)
    
    def extract_from_open_interest(
        self,
        oi_list: List[Dict]
    ) -> np.ndarray:
        """
        Извлечение признаков из открытого интереса.
        
        Returns:
            Массив признаков: [oi, oi_change, oi_value]
        """
        if not oi_list:
            return np.zeros(3)
        
        last_oi = oi_list[-1]
        oi = float(last_oi.get("open_interest", 0))
        oi_value = float(last_oi.get("open_interest_value", 0)) if last_oi.get("open_interest_value") is not None else 0.0
        
        # OI change
        if len(oi_list) >= 2:
            prev_oi = float(oi_list[-2].get("open_interest", oi))
            oi_change = (oi - prev_oi) / max(prev_oi, 1e-10)
        else:
            oi_change = 0.0
        
        return np.array([oi, oi_change, oi_value])
    
    def extract_from_liquidations(
        self,
        liquidations: List[Dict],
        window_sec: int = 60
    ) -> np.ndarray:
        """
        Извлечение признаков из ликвидаций.
        
        Returns:
            Массив признаков: [liq_volume, liq_rate, buy_liq_ratio]
        """
        if not liquidations:
            return np.zeros(3)
        
        # Объем ликвидаций
        liq_volume = sum(float(liq.get("quantity", 0)) for liq in liquidations)
        
        # Rate (ликвидаций в секунду)
        if len(liquidations) >= 2:
            time_span = (liquidations[-1].get("ts", 0) - liquidations[0].get("ts", 0)) / 1000.0
            liq_rate = len(liquidations) / max(time_span, 1.0)
        else:
            liq_rate = 0.0
        
        # Buy/Sell ratio
        buy_liq = sum(
            float(liq.get("quantity", 0))
            for liq in liquidations
            if str(liq.get("side", "")).lower().startswith("b")
        )
        buy_liq_ratio = buy_liq / max(liq_volume, 1e-10)
        
        return np.array([liq_volume, liq_rate, buy_liq_ratio])
    
    def combine_features(
        self,
        trades: List[Dict],
        orderbook: Optional[Dict],
        klines: List[Dict],
        oi_list: List[Dict],
        liquidations: List[Dict],
    ) -> np.ndarray:
        """
        Объединение всех признаков в единый вектор.
        
        Returns:
            Массив shape (num_features,) - объединенные признаки
        """
        trade_features = self.extract_from_trades(trades)
        orderbook_features = self.extract_from_orderbook(orderbook) if orderbook else np.zeros(5)
        kline_features = self.extract_from_kline(klines)
        oi_features = self.extract_from_open_interest(oi_list)
        liq_features = self.extract_from_liquidations(liquidations)
        
        # Объединяем все признаки
        combined = np.concatenate([
            trade_features,      # 7 features
            orderbook_features,   # 5 features
            kline_features,      # 5-8 features
            oi_features,         # 3 features
            liq_features,        # 3 features
        ])
        
        return combined
    
    def _calculate_rsi(self, klines: List[Dict], period: int = 14) -> float:
        """Упрощенный расчет RSI."""
        if len(klines) < period + 1:
            return 50.0
        
        closes = [float(k.get("close", 0)) for k in klines[-period-1:]]
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(change))
        
        avg_gain = np.mean(gains) if gains else 0.0
        avg_loss = np.mean(losses) if losses else 1e-10
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi / 100.0  # Нормализуем к [0, 1]
    
    def _calculate_macd(self, klines: List[Dict], fast: int = 12, slow: int = 26) -> float:
        """Упрощенный расчет MACD."""
        if len(klines) < slow:
            return 0.0
        
        closes = [float(k.get("close", 0)) for k in klines[-slow:]]
        
        # Простое скользящее среднее
        fast_ma = np.mean(closes[-fast:]) if len(closes) >= fast else np.mean(closes)
        slow_ma = np.mean(closes)
        
        macd = (fast_ma - slow_ma) / max(slow_ma, 1e-10)
        return macd
