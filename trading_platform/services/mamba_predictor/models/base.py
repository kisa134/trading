"""
Base Mamba model for time series forecasting.
"""
import torch
import torch.nn as nn
from typing import Optional

try:
    from mamba_ssm import Mamba2
    MAMBA_AVAILABLE = True
except ImportError:
    try:
        from mamba_ssm.modules.mamba_simple import Mamba
        MAMBA_AVAILABLE = True
        Mamba2 = Mamba  # Fallback to Mamba v1
    except ImportError:
        MAMBA_AVAILABLE = False
        Mamba2 = None


class MambaForecaster(nn.Module):
    """
    Базовая Mamba модель для прогнозирования временных рядов.
    
    Args:
        input_features: Количество входных признаков
        hidden_dim: Размерность скрытого слоя
        d_state: Размерность состояния State Space Model
        d_conv: Размерность конволюции
        expand: Коэффициент расширения
        output_features: Количество выходных признаков
    """
    
    def __init__(
        self,
        input_features: int = 20,
        hidden_dim: int = 256,
        d_state: int = 64,
        d_conv: int = 4,
        expand: int = 2,
        output_features: int = 3,
    ):
        super().__init__()
        
        if not MAMBA_AVAILABLE:
            raise ImportError(
                "mamba-ssm is not installed. Install it with: pip install mamba-ssm"
            )
        
        self.input_features = input_features
        self.hidden_dim = hidden_dim
        self.output_features = output_features
        
        # Encoder: проекция входных признаков в скрытое пространство
        self.encoder = nn.Linear(input_features, hidden_dim)
        
        # Mamba блок
        self.mamba = Mamba2(
            d_model=hidden_dim,
            d_state=d_state,
            d_conv=d_conv,
            expand=expand,
        )
        
        # Decoder: проекция из скрытого пространства в выход
        self.decoder = nn.Linear(hidden_dim, output_features)
        
        # Layer normalization для стабильности
        self.layer_norm = nn.LayerNorm(hidden_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        
        Args:
            x: Input tensor of shape (batch, seq_len, input_features)
        
        Returns:
            Output tensor of shape (batch, output_features)
        """
        # x: (batch, seq_len, input_features)
        x = self.encoder(x)  # (batch, seq_len, hidden_dim)
        x = self.layer_norm(x)
        x = self.mamba(x)  # (batch, seq_len, hidden_dim)
        x = x[:, -1, :]  # Берем последний таймстеп (batch, hidden_dim)
        x = self.decoder(x)  # (batch, output_features)
        return x


class SimpleLSTMForecaster(nn.Module):
    """
    Fallback LSTM модель, если Mamba недоступна.
    Используется для тестирования без установки mamba-ssm.
    """
    
    def __init__(
        self,
        input_features: int = 20,
        hidden_dim: int = 256,
        output_features: int = 3,
        num_layers: int = 2,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_features,
            hidden_dim,
            num_layers=num_layers,
            batch_first=True,
        )
        self.decoder = nn.Linear(hidden_dim, output_features)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        out = out[:, -1, :]
        return self.decoder(out)
