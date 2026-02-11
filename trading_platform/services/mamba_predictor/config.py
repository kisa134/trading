"""
Configuration for Mamba Prediction Service.
"""
import os

# Sequence and model parameters
SEQUENCE_LENGTH = 200  # Длина последовательности для Mamba
TIMEFRAMES = ["1m", "5m", "15m"]  # Мульти-таймфрейм прогнозы
INPUT_FEATURES = 25  # Общее количество признаков (trades + orderbook + kline + OI + liquidations)
HIDDEN_DIM = 256  # Размерность скрытого слоя Mamba
D_STATE = 64  # Размерность состояния State Space Model
D_CONV = 4  # Размерность конволюции
EXPAND = 2  # Коэффициент расширения

# Prediction settings
PREDICTION_INTERVAL_SEC = 5  # Как часто делать предсказания (секунды)
MIN_SEQUENCE_LENGTH = 50  # Минимальная длина последовательности для предсказания

# Model paths
MODEL_CHECKPOINT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "models", "checkpoints"
)
MODEL_BASE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models")

# Device
DEVICE = "cuda" if os.environ.get("CUDA_AVAILABLE", "false").lower() == "true" else "cpu"

# Feature extraction settings
TRADES_WINDOW_SEC = 60  # Окно для агрегации trades (секунды)
ORDERBOOK_DEPTH = 20  # Глубина стакана для анализа
TECHNICAL_INDICATORS = True  # Использовать технические индикаторы (RSI, MACD)

# Training settings
BATCH_SIZE = 32
LEARNING_RATE = 1e-4
NUM_EPOCHS = 100
VALIDATION_SPLIT = 0.2
EARLY_STOPPING_PATIENCE = 10

# Redis settings
REDIS_STREAM_BLOCK_MS = 1000  # Блокировка при чтении из Redis Streams
REDIS_BUFFER_SIZE = 1000  # Размер буфера для накопления данных
