"""
Normalization utilities for feature vectors.
"""
import numpy as np
from typing import Optional, Tuple
from sklearn.preprocessing import StandardScaler, MinMaxScaler
import pickle
import os


class FeatureNormalizer:
    """
    Нормализация признаков для Mamba модели.
    Поддерживает StandardScaler (z-score) и MinMaxScaler.
    """
    
    def __init__(
        self,
        method: str = "standard",  # "standard" или "minmax"
        fit_on_init: bool = False,
        feature_stats: Optional[dict] = None,
    ):
        self.method = method
        if method == "standard":
            self.scaler = StandardScaler()
        elif method == "minmax":
            self.scaler = MinMaxScaler()
        else:
            raise ValueError(f"Unknown normalization method: {method}")
        
        self.is_fitted = False
        self.feature_stats = feature_stats or {}
        
        if fit_on_init and feature_stats:
            self._load_stats()
    
    def fit(self, X: np.ndarray) -> None:
        """
        Обучение нормализатора на данных.
        
        Args:
            X: Массив shape (n_samples, n_features) или (n_samples, seq_len, n_features)
        """
        # Если 3D, flatten для обучения
        if X.ndim == 3:
            X_flat = X.reshape(-1, X.shape[-1])
        else:
            X_flat = X
        
        self.scaler.fit(X_flat)
        self.is_fitted = True
        
        # Сохраняем статистику
        if hasattr(self.scaler, "mean_"):
            self.feature_stats["mean"] = self.scaler.mean_.tolist()
            self.feature_stats["std"] = self.scaler.scale_.tolist()
        if hasattr(self.scaler, "min_"):
            self.feature_stats["min"] = self.scaler.min_.tolist()
            self.feature_stats["max"] = self.scaler.data_max_.tolist()
    
    def transform(self, X: np.ndarray) -> np.ndarray:
        """
        Нормализация данных.
        
        Args:
            X: Массив shape (n_samples, n_features) или (n_samples, seq_len, n_features)
        
        Returns:
            Нормализованный массив той же формы
        """
        if not self.is_fitted:
            raise ValueError("Normalizer must be fitted before transform")
        
        original_shape = X.shape
        
        # Flatten для нормализации
        if X.ndim == 3:
            X_flat = X.reshape(-1, X.shape[-1])
        else:
            X_flat = X
        
        X_normalized = self.scaler.transform(X_flat)
        
        # Восстанавливаем форму
        return X_normalized.reshape(original_shape)
    
    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        """Обучение и нормализация."""
        self.fit(X)
        return self.transform(X)
    
    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        """
        Обратная нормализация (для восстановления исходных значений).
        
        Args:
            X: Нормализованный массив
        
        Returns:
            Денормализованный массив
        """
        if not self.is_fitted:
            raise ValueError("Normalizer must be fitted before inverse_transform")
        
        original_shape = X.shape
        
        if X.ndim == 3:
            X_flat = X.reshape(-1, X.shape[-1])
        else:
            X_flat = X
        
        X_denormalized = self.scaler.inverse_transform(X_flat)
        
        return X_denormalized.reshape(original_shape)
    
    def save(self, path: str) -> None:
        """Сохранение нормализатора."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "scaler": self.scaler,
                "method": self.method,
                "is_fitted": self.is_fitted,
                "feature_stats": self.feature_stats,
            }, f)
    
    def load(self, path: str) -> None:
        """Загрузка нормализатора."""
        with open(path, "rb") as f:
            data = pickle.load(f)
            self.scaler = data["scaler"]
            self.method = data["method"]
            self.is_fitted = data["is_fitted"]
            self.feature_stats = data.get("feature_stats", {})
    
    def _load_stats(self) -> None:
        """Загрузка статистики из feature_stats."""
        if not self.feature_stats:
            return
        
        if self.method == "standard" and "mean" in self.feature_stats:
            # Восстанавливаем StandardScaler
            mean = np.array(self.feature_stats["mean"])
            std = np.array(self.feature_stats["std"])
            self.scaler.mean_ = mean
            self.scaler.scale_ = std
            self.scaler.var_ = std ** 2
            self.is_fitted = True
        elif self.method == "minmax" and "min" in self.feature_stats:
            # Восстанавливаем MinMaxScaler
            min_vals = np.array(self.feature_stats["min"])
            max_vals = np.array(self.feature_stats["max"])
            self.scaler.min_ = min_vals
            self.scaler.data_max_ = max_vals
            self.scaler.data_min_ = min_vals
            self.scaler.data_range_ = max_vals - min_vals
            self.is_fitted = True


class SimpleNormalizer:
    """
    Простая нормализация без обучения (использует текущие статистики).
    Полезно для real-time обработки без предварительного обучения.
    """
    
    @staticmethod
    def normalize_features(features: np.ndarray, method: str = "minmax") -> np.ndarray:
        """
        Простая нормализация признаков.
        
        Args:
            features: Массив признаков
            method: "minmax" или "standard"
        
        Returns:
            Нормализованный массив
        """
        if method == "minmax":
            # Min-max нормализация к [0, 1]
            min_vals = np.min(features, axis=0, keepdims=True)
            max_vals = np.max(features, axis=0, keepdims=True)
            range_vals = max_vals - min_vals
            range_vals[range_vals == 0] = 1.0  # Избегаем деления на ноль
            return (features - min_vals) / range_vals
        elif method == "standard":
            # Z-score нормализация
            mean = np.mean(features, axis=0, keepdims=True)
            std = np.std(features, axis=0, keepdims=True)
            std[std == 0] = 1.0  # Избегаем деления на ноль
            return (features - mean) / std
        else:
            raise ValueError(f"Unknown method: {method}")
