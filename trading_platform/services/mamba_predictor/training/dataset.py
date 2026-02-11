"""
Dataset for training Mamba models on historical data.
"""
import torch
from torch.utils.data import Dataset
import numpy as np
from typing import List, Dict, Optional
import json
import asyncpg
import redis.asyncio as redis


class TradingDataset(Dataset):
    """
    Dataset для обучения Mamba модели на исторических данных.
    """
    
    def __init__(
        self,
        features: np.ndarray,
        directions: np.ndarray,
        prices: np.ndarray,
    ):
        """
        Args:
            features: Массив признаков shape (n_samples, seq_len, n_features)
            directions: Массив направлений shape (n_samples,) - 0 = short, 1 = long
            prices: Массив цен shape (n_samples,) - целевая цена для регрессии
        """
        self.features = torch.tensor(features, dtype=torch.float32)
        self.directions = torch.tensor(directions, dtype=torch.long)
        self.prices = torch.tensor(prices, dtype=torch.float32)
    
    def __len__(self) -> int:
        return len(self.features)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        return {
            "features": self.features[idx],
            "direction": self.directions[idx],
            "price": self.prices[idx],
        }


async def load_data_from_redis(
    redis_url: str,
    exchange: str,
    symbol: str,
    sequence_length: int,
    limit: int = 10000,
) -> tuple:
    """
    Загрузка данных из Redis для обучения.
    
    Returns:
        (features, directions, prices) - numpy arrays
    """
    r = redis.from_url(redis_url, decode_responses=True)
    
    # Загружаем данные из Redis Streams
    from shared.streams import (
        STREAM_TRADES,
        STREAM_KLINE,
        STREAM_OPEN_INTEREST,
        REDIS_KEY_DOM,
    )
    from services.mamba_predictor.preprocessing.feature_extractor import MarketFeatureExtractor
    
    extractor = MarketFeatureExtractor()
    
    # Читаем trades
    trades_messages = await r.xrevrange(STREAM_TRADES, count=limit * 2)
    trades = []
    for _mid, fields in trades_messages or []:
        payload_str = (fields or {}).get("payload")
        if payload_str:
            try:
                trade = json.loads(payload_str)
                if trade.get("exchange") == exchange and trade.get("symbol") == symbol:
                    trades.append(trade)
            except:
                pass
    
    # Читаем kline
    kline_messages = await r.xrevrange(STREAM_KLINE, count=limit * 2)
    klines = []
    for _mid, fields in kline_messages or []:
        payload_str = (fields or {}).get("payload")
        if payload_str:
            try:
                kline = json.loads(payload_str)
                if kline.get("exchange") == exchange and kline.get("symbol") == symbol:
                    klines.append(kline)
            except:
                pass
    
    # Сортируем по времени
    trades.sort(key=lambda x: x.get("ts", 0))
    klines.sort(key=lambda x: x.get("start", 0))
    
    # Создаем последовательности
    features_list = []
    directions_list = []
    prices_list = []
    
    for i in range(sequence_length, len(trades)):
        # Берем окно данных
        trades_window = trades[i - sequence_length:i]
        kline_window = [k for k in klines if trades[i - sequence_length].get("ts", 0) <= k.get("start", 0) <= trades[i].get("ts", 0)]
        
        # Получаем текущий orderbook (упрощенно - используем последний)
        dom_key = REDIS_KEY_DOM.format(exchange=exchange, symbol=symbol)
        dom_raw = await r.get(dom_key)
        orderbook = None
        if dom_raw:
            try:
                orderbook = json.loads(dom_raw)
            except:
                pass
        
        # Извлекаем признаки
        features = extractor.combine_features(
            trades=trades_window,
            orderbook=orderbook,
            klines=kline_window,
            oi_list=[],
            liquidations=[],
        )
        
        # Определяем направление (сравниваем текущую цену с будущей)
        if i < len(trades) - 1:
            current_price = float(trades[i].get("price", 0))
            future_price = float(trades[i + 1].get("price", 0))
            direction = 1 if future_price > current_price else 0
            target_price = future_price
        else:
            direction = 0
            target_price = float(trades[i].get("price", 0))
        
        features_list.append(features)
        directions_list.append(direction)
        prices_list.append(target_price)
    
    await r.aclose()
    
    if not features_list:
        return np.array([]), np.array([]), np.array([])
    
    # Преобразуем в массивы
    features_array = np.array(features_list)
    directions_array = np.array(directions_list)
    prices_array = np.array(prices_list)
    
    return features_array, directions_array, prices_array


async def load_data_from_postgres(
    db_url: str,
    exchange: str,
    symbol: str,
    sequence_length: int,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
) -> tuple:
    """
    Загрузка данных из PostgreSQL для обучения.
    
    Returns:
        (features, directions, prices) - numpy arrays
    """
    conn = await asyncpg.connect(db_url)
    
    try:
        # Загружаем trades
        query = "SELECT side, price, size, ts FROM trades WHERE exchange=$1 AND symbol=$2"
        params = [exchange, symbol]
        
        if from_ts:
            query += " AND ts >= $3"
            params.append(from_ts)
        if to_ts:
            query += f" AND ts <= ${len(params) + 1}"
            params.append(to_ts)
        
        query += " ORDER BY ts LIMIT 50000"
        
        rows = await conn.fetch(query, *params)
        trades = [
            {
                "side": r["side"],
                "price": float(r["price"]),
                "size": float(r["size"]),
                "ts": r["ts"],
            }
            for r in rows
        ]
        
    finally:
        await conn.close()
    
    # Аналогично load_data_from_redis, создаем последовательности
    # (упрощенная версия - в реальности нужна более сложная логика)
    from services.mamba_predictor.preprocessing.feature_extractor import MarketFeatureExtractor
    
    extractor = MarketFeatureExtractor()
    features_list = []
    directions_list = []
    prices_list = []
    
    for i in range(sequence_length, len(trades)):
        trades_window = trades[i - sequence_length:i]
        
        features = extractor.combine_features(
            trades=trades_window,
            orderbook=None,
            klines=[],
            oi_list=[],
            liquidations=[],
        )
        
        if i < len(trades) - 1:
            current_price = trades[i]["price"]
            future_price = trades[i + 1]["price"]
            direction = 1 if future_price > current_price else 0
            target_price = future_price
        else:
            direction = 0
            target_price = trades[i]["price"]
        
        features_list.append(features)
        directions_list.append(direction)
        prices_list.append(target_price)
    
    if not features_list:
        return np.array([]), np.array([]), np.array([])
    
    features_array = np.array(features_list)
    directions_array = np.array(directions_list)
    prices_array = np.array(prices_list)
    
    return features_array, directions_array, prices_array
