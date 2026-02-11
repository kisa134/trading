"""
Multi-head Mamba model for direction classification and price regression.
"""
import torch
import torch.nn as nn
from typing import Dict

from .base import MambaForecaster


class MultiHeadMambaPredictor(nn.Module):
    """
    Multi-head модель для одновременного предсказания направления и цены.
    
    Использует общий Mamba backbone и два отдельных head:
    - Direction head: бинарная классификация (Long/Short)
    - Price head: регрессия цены
    """
    
    def __init__(
        self,
        input_features: int = 20,
        hidden_dim: int = 256,
        d_state: int = 64,
        d_conv: int = 4,
        expand: int = 2,
    ):
        super().__init__()
        
        # Общий Mamba backbone (без decoder)
        self.shared_mamba = MambaForecaster(
            input_features=input_features,
            hidden_dim=hidden_dim,
            d_state=d_state,
            d_conv=d_conv,
            expand=expand,
            output_features=hidden_dim,  # Возвращаем features, а не финальный выход
        )
        
        # Direction head: бинарная классификация
        self.direction_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 2),  # [long_prob, short_prob]
            nn.Softmax(dim=1)
        )
        
        # Price head: регрессия
        self.price_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 1)  # Цена
        )
    
    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Forward pass.
        
        Args:
            x: Input tensor of shape (batch, seq_len, input_features)
        
        Returns:
            Dictionary with:
                - direction: (batch, 2) - probabilities [long, short]
                - price: (batch, 1) - predicted price
        """
        # Получаем features из shared Mamba
        features = self.shared_mamba(x)  # (batch, hidden_dim)
        
        # Применяем heads
        direction = self.direction_head(features)  # (batch, 2)
        price = self.price_head(features)  # (batch, 1)
        
        return {
            "direction": direction,
            "price": price.squeeze(-1),  # (batch,)
        }


class DirectionClassifier(nn.Module):
    """
    Отдельная модель только для классификации направления.
    """
    
    def __init__(
        self,
        input_features: int = 20,
        hidden_dim: int = 256,
        d_state: int = 64,
        d_conv: int = 4,
        expand: int = 2,
    ):
        super().__init__()
        self.mamba = MambaForecaster(
            input_features=input_features,
            hidden_dim=hidden_dim,
            d_state=d_state,
            d_conv=d_conv,
            expand=expand,
            output_features=hidden_dim,
        )
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 2),
            nn.Softmax(dim=1)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.mamba(x)
        return self.classifier(features)


class PriceRegressor(nn.Module):
    """
    Отдельная модель только для регрессии цены.
    """
    
    def __init__(
        self,
        input_features: int = 20,
        hidden_dim: int = 256,
        d_state: int = 64,
        d_conv: int = 4,
        expand: int = 2,
    ):
        super().__init__()
        self.mamba = MambaForecaster(
            input_features=input_features,
            hidden_dim=hidden_dim,
            d_state=d_state,
            d_conv=d_conv,
            expand=expand,
            output_features=hidden_dim,
        )
        self.regressor = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 1)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.mamba(x)
        return self.regressor(features).squeeze(-1)
