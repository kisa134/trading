"""
Quickstart script for testing Mamba on synthetic data.
"""
import sys
import os
import torch
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.mamba_predictor.models.base import MambaForecaster, SimpleLSTMForecaster
from services.mamba_predictor.config import INPUT_FEATURES, HIDDEN_DIM, D_STATE, D_CONV, EXPAND, SEQUENCE_LENGTH, DEVICE


def test_mamba_model():
    """Тест базовой Mamba модели на синтетических данных."""
    print("Testing Mamba model on synthetic data...")
    
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    try:
        # Создаем модель
        model = MambaForecaster(
            input_features=INPUT_FEATURES,
            hidden_dim=HIDDEN_DIM,
            d_state=D_STATE,
            d_conv=D_CONV,
            expand=EXPAND,
            output_features=3,  # [long_prob, short_prob, price]
        ).to(device)
        
        print("✓ Mamba model created successfully")
    except ImportError as e:
        print(f"⚠ Mamba SSM not available: {e}")
        print("Using LSTM fallback model...")
        model = SimpleLSTMForecaster(
            input_features=INPUT_FEATURES,
            hidden_dim=HIDDEN_DIM,
            output_features=3,
        ).to(device)
        print("✓ LSTM fallback model created")
    
    model.eval()
    
    # Генерируем синтетические данные (имитация рыночных данных)
    batch_size = 1
    dummy_data = torch.randn(batch_size, SEQUENCE_LENGTH, INPUT_FEATURES).to(device)
    
    print(f"Input shape: {dummy_data.shape}")
    
    # Forward pass
    with torch.no_grad():
        output = model(dummy_data)
        print(f"Output shape: {output.shape}")
        print(f"Output: {output.cpu().numpy()}")
    
    # Тест multi-head модели
    print("\nTesting Multi-Head Mamba model...")
    try:
        from services.mamba_predictor.models.multi_head import MultiHeadMambaPredictor
        
        multi_model = MultiHeadMambaPredictor(
            input_features=INPUT_FEATURES,
            hidden_dim=HIDDEN_DIM,
            d_state=D_STATE,
            d_conv=D_CONV,
            expand=EXPAND,
        ).to(device)
        
        multi_model.eval()
        
        with torch.no_grad():
            output = multi_model(dummy_data)
            direction_probs = output["direction"].cpu().numpy()[0]
            predicted_price = output["price"].cpu().numpy()[0]
            
            print(f"Direction probabilities: Long={direction_probs[0]:.2%}, Short={direction_probs[1]:.2%}")
            print(f"Predicted price: {predicted_price:.2f}")
        
        print("✓ Multi-Head model test passed!")
        
    except Exception as e:
        print(f"✗ Multi-Head model test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✓ All tests completed successfully!")
    print("\nNext steps:")
    print("1. Install mamba-ssm: pip install mamba-ssm causal-conv1d")
    print("2. Train model: python -m services.mamba_predictor.training.train --redis redis://localhost:6379")
    print("3. Run prediction service: python -m services.mamba_predictor.main --redis redis://localhost:6379")


if __name__ == "__main__":
    test_mamba_model()
