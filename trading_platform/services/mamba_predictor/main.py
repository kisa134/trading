"""
Mamba Prediction Service: real-time price forecasting from Redis Streams.
"""
import asyncio
import json
import argparse
import sys
import os
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import redis.asyncio as redis
import torch
import numpy as np

from shared.streams import (
    STREAM_TRADES,
    STREAM_ORDERBOOK_UPDATES,
    STREAM_KLINE,
    STREAM_OPEN_INTEREST,
    STREAM_LIQUIDATIONS,
    STREAM_MAMBA_PREDICTIONS,
    REDIS_KEY_DOM,
    REDIS_KEY_MAMBA_PREDICTIONS,
)
from shared.schemas import EXCHANGE_FIELD, SYMBOL_FIELD

from .config import (
    SEQUENCE_LENGTH,
    PREDICTION_INTERVAL_SEC,
    MIN_SEQUENCE_LENGTH,
    INPUT_FEATURES,
    HIDDEN_DIM,
    D_STATE,
    D_CONV,
    EXPAND,
    DEVICE,
    REDIS_STREAM_BLOCK_MS,
)
from .models.multi_head import MultiHeadMambaPredictor
from .preprocessing.feature_extractor import MarketFeatureExtractor
from .preprocessing.normalizer import SimpleNormalizer


class MambaPredictionService:
    """
    Основной сервис для real-time прогнозирования через Mamba SSM.
    """
    
    def __init__(
        self,
        redis_url: str,
        exchange: str = "bybit",
        symbol: str = "BTCUSDT",
        model_path: Optional[str] = None,
    ):
        self.redis_url = redis_url
        self.exchange = exchange
        self.symbol = symbol
        self.redis: Optional[redis.Redis] = None
        
        # Буферы для накопления данных
        self.trades_buffer: deque = deque(maxlen=SEQUENCE_LENGTH * 2)
        self.orderbook_buffer: deque = deque(maxlen=SEQUENCE_LENGTH)
        self.kline_buffer: deque = deque(maxlen=SEQUENCE_LENGTH)
        self.oi_buffer: deque = deque(maxlen=SEQUENCE_LENGTH)
        self.liquidations_buffer: deque = deque(maxlen=SEQUENCE_LENGTH)
        
        # Feature extractor и normalizer
        self.feature_extractor = MarketFeatureExtractor()
        self.normalizer = SimpleNormalizer()
        
        # Модель
        self.device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
        self.model = self._load_model(model_path)
        self.model.eval()
        
        # Таймеры для предсказаний
        self.last_prediction_time = 0.0
        
        print(f"[mamba_predictor] Initialized for {exchange}/{symbol} on {self.device}")
    
    def _load_model(self, model_path: Optional[str]) -> torch.nn.Module:
        """Загрузка модели (или создание новой, если путь не указан)."""
        model = MultiHeadMambaPredictor(
            input_features=INPUT_FEATURES,
            hidden_dim=HIDDEN_DIM,
            d_state=D_STATE,
            d_conv=D_CONV,
            expand=EXPAND,
        )
        
        if model_path and os.path.exists(model_path):
            try:
                checkpoint = torch.load(model_path, map_location=self.device)
                model.load_state_dict(checkpoint.get("model_state_dict", checkpoint))
                print(f"[mamba_predictor] Loaded model from {model_path}")
            except Exception as e:
                print(f"[mamba_predictor] Failed to load model: {e}, using untrained model")
        else:
            print("[mamba_predictor] Using untrained model (random weights)")
        
        return model.to(self.device)
    
    async def consume_streams(self):
        """Чтение данных из Redis Streams и накопление в буферы."""
        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        
        last_ids = {
            STREAM_TRADES: "$",
            STREAM_ORDERBOOK_UPDATES: "$",
            STREAM_KLINE: "$",
            STREAM_OPEN_INTEREST: "$",
            STREAM_LIQUIDATIONS: "$",
        }
        
        while True:
            try:
                result = await self.redis.xread(
                    last_ids,
                    count=50,
                    block=REDIS_STREAM_BLOCK_MS,
                )
                
                if not result:
                    continue
                
                for stream_name, messages in result:
                    for msg_id, fields in messages:
                        last_ids[stream_name] = msg_id
                        payload_str = (fields or {}).get("payload")
                        if not payload_str:
                            continue
                        
                        try:
                            payload = json.loads(payload_str)
                        except json.JSONDecodeError:
                            continue
                        
                        # Фильтрация по exchange и symbol
                        if payload.get(EXCHANGE_FIELD) != self.exchange:
                            continue
                        if payload.get(SYMBOL_FIELD) != self.symbol:
                            continue
                        
                        # Добавление в соответствующий буфер
                        if stream_name == STREAM_TRADES:
                            self.trades_buffer.append(payload)
                        elif stream_name == STREAM_ORDERBOOK_UPDATES:
                            self.orderbook_buffer.append(payload)
                        elif stream_name == STREAM_KLINE:
                            self.kline_buffer.append(payload)
                        elif stream_name == STREAM_OPEN_INTEREST:
                            self.oi_buffer.append(payload)
                        elif stream_name == STREAM_LIQUIDATIONS:
                            self.liquidations_buffer.append(payload)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[mamba_predictor] Error in consume_streams: {e}")
                await asyncio.sleep(1)
    
    async def prediction_loop(self):
        """Основной цикл предсказаний."""
        while True:
            try:
                current_time = time.time()
                
                # Проверяем, нужно ли делать предсказание
                if current_time - self.last_prediction_time >= PREDICTION_INTERVAL_SEC:
                    if len(self.trades_buffer) >= MIN_SEQUENCE_LENGTH:
                        prediction = await self.predict()
                        if prediction:
                            await self.publish_prediction(prediction)
                            self.last_prediction_time = current_time
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[mamba_predictor] Error in prediction_loop: {e}")
                await asyncio.sleep(1)
    
    async def predict(self) -> Optional[Dict]:
        """
        Создание предсказания на основе накопленных данных.
        
        Returns:
            Словарь с предсказанием или None при ошибке
        """
        try:
            # Получаем текущий DOM для orderbook
            dom_key = REDIS_KEY_DOM.format(exchange=self.exchange, symbol=self.symbol)
            dom_raw = await self.redis.get(dom_key)
            current_orderbook = None
            if dom_raw:
                try:
                    current_orderbook = json.loads(dom_raw)
                except:
                    pass
            
            # Если нет orderbook в буфере, используем текущий DOM
            if not self.orderbook_buffer and current_orderbook:
                orderbook_data = current_orderbook
            elif self.orderbook_buffer:
                orderbook_data = self.orderbook_buffer[-1]
            else:
                orderbook_data = None
            
            # Извлекаем признаки для последовательности
            sequence_features = []
            
            # Берем последние SEQUENCE_LENGTH элементов из каждого буфера
            trades_window = list(self.trades_buffer)[-SEQUENCE_LENGTH:] if len(self.trades_buffer) >= SEQUENCE_LENGTH else list(self.trades_buffer)
            kline_window = list(self.kline_buffer)[-SEQUENCE_LENGTH:] if len(self.kline_buffer) >= SEQUENCE_LENGTH else list(self.kline_buffer)
            oi_window = list(self.oi_buffer)[-SEQUENCE_LENGTH:] if len(self.oi_buffer) >= SEQUENCE_LENGTH else list(self.oi_buffer)
            liq_window = list(self.liquidations_buffer)[-SEQUENCE_LENGTH:] if len(self.liquidations_buffer) >= SEQUENCE_LENGTH else list(self.liquidations_buffer)
            
            # Если недостаточно данных, возвращаем None
            if len(trades_window) < MIN_SEQUENCE_LENGTH:
                return None
            
            # Извлекаем признаки для каждого временного шага
            for i in range(len(trades_window)):
                # Для каждого шага берем соответствующие данные
                trades_slice = trades_window[:i+1] if i < len(trades_window) else trades_window
                kline_slice = kline_window[:i+1] if i < len(kline_window) else kline_window
                oi_slice = oi_window[:i+1] if i < len(oi_window) else oi_window
                liq_slice = liq_window[:i+1] if i < len(liq_window) else liq_window
                
                # Извлекаем признаки
                features = self.feature_extractor.combine_features(
                    trades=trades_slice,
                    orderbook=orderbook_data if i == len(trades_window) - 1 else None,
                    klines=kline_slice,
                    oi_list=oi_slice,
                    liquidations=liq_slice,
                )
                
                sequence_features.append(features)
            
            # Если недостаточно признаков, дополняем нулями
            while len(sequence_features) < SEQUENCE_LENGTH:
                sequence_features.insert(0, np.zeros(INPUT_FEATURES))
            
            # Берем последние SEQUENCE_LENGTH
            sequence_features = sequence_features[-SEQUENCE_LENGTH:]
            
            # Преобразуем в numpy массив
            features_array = np.array(sequence_features)  # (seq_len, n_features)
            
            # Нормализация
            features_normalized = self.normalizer.normalize_features(features_array, method="minmax")
            
            # Преобразуем в tensor
            features_tensor = torch.tensor(
                features_normalized,
                dtype=torch.float32,
            ).unsqueeze(0).to(self.device)  # (1, seq_len, n_features)
            
            # Inference
            with torch.no_grad():
                output = self.model(features_tensor)
            
            # Извлекаем результаты
            direction_probs = output["direction"].cpu().numpy()[0]  # [long_prob, short_prob]
            predicted_price = float(output["price"].cpu().numpy()[0])
            
            # Определяем направление
            long_prob = float(direction_probs[0])
            short_prob = float(direction_probs[1])
            direction = "long" if long_prob > short_prob else "short"
            confidence = max(long_prob, short_prob)
            
            # Получаем текущую цену для контекста
            current_price = None
            if trades_window:
                current_price = float(trades_window[-1].get("price", 0))
            elif orderbook_data and orderbook_data.get("bids") and orderbook_data.get("asks"):
                best_bid = float(orderbook_data["bids"][0][0])
                best_ask = float(orderbook_data["asks"][0][0])
                current_price = (best_bid + best_ask) / 2
            
            prediction = {
                "exchange": self.exchange,
                "symbol": self.symbol,
                "ts": int(time.time() * 1000),
                "direction": direction,
                "confidence": confidence,
                "long_prob": long_prob,
                "short_prob": short_prob,
                "predicted_price": predicted_price,
                "current_price": current_price,
                "price_change_pct": (predicted_price - current_price) / current_price * 100 if current_price else 0.0,
            }
            
            return prediction
            
        except Exception as e:
            print(f"[mamba_predictor] Error in predict: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def publish_prediction(self, prediction: Dict):
        """Публикация предсказания в Redis Stream."""
        try:
            payload = json.dumps(prediction)
            await self.redis.xadd(
                STREAM_MAMBA_PREDICTIONS,
                {"payload": payload},
                maxlen=1000,
            )
            
            # Также сохраняем в Redis Key для быстрого доступа
            key = REDIS_KEY_MAMBA_PREDICTIONS.format(
                exchange=self.exchange,
                symbol=self.symbol,
            )
            await self.redis.set(key, payload, ex=60)  # TTL 60 секунд
            
            print(f"[mamba_predictor] Published prediction: {prediction['direction']} ({prediction['confidence']:.2%})")
            
        except Exception as e:
            print(f"[mamba_predictor] Error publishing prediction: {e}")
    
    async def run(self):
        """Запуск сервиса."""
        print(f"[mamba_predictor] Starting service for {self.exchange}/{self.symbol}")
        
        # Запускаем два параллельных процесса
        await asyncio.gather(
            self.consume_streams(),
            self.prediction_loop(),
        )


async def main():
    parser = argparse.ArgumentParser(description="Mamba Prediction Service")
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--exchange", default="bybit", help="Exchange name")
    parser.add_argument("--symbol", default="BTCUSDT", help="Symbol")
    parser.add_argument("--model", default=None, help="Path to model checkpoint")
    args = parser.parse_args()
    
    service = MambaPredictionService(
        redis_url=args.redis,
        exchange=args.exchange,
        symbol=args.symbol,
        model_path=args.model,
    )
    
    try:
        await service.run()
    except KeyboardInterrupt:
        print("[mamba_predictor] Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
