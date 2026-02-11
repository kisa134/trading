"""
Training script for Mamba prediction models.
"""
import argparse
import asyncio
import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from services.mamba_predictor.models.multi_head import MultiHeadMambaPredictor
from services.mamba_predictor.training.dataset import TradingDataset, load_data_from_redis, load_data_from_postgres
from services.mamba_predictor.training.metrics import evaluate_model
from services.mamba_predictor.config import (
    SEQUENCE_LENGTH,
    INPUT_FEATURES,
    HIDDEN_DIM,
    D_STATE,
    D_CONV,
    EXPAND,
    BATCH_SIZE,
    LEARNING_RATE,
    NUM_EPOCHS,
    VALIDATION_SPLIT,
    EARLY_STOPPING_PATIENCE,
    MODEL_CHECKPOINT_PATH,
    DEVICE,
)
from services.mamba_predictor.preprocessing.normalizer import FeatureNormalizer


class CombinedLoss(nn.Module):
    """
    Комбинированная функция потерь для direction classification и price regression.
    """
    
    def __init__(self, direction_weight: float = 1.0, price_weight: float = 1.0):
        super().__init__()
        self.direction_weight = direction_weight
        self.price_weight = price_weight
        self.ce_loss = nn.CrossEntropyLoss()
        self.mse_loss = nn.MSELoss()
    
    def forward(
        self,
        direction_pred: torch.Tensor,
        direction_true: torch.Tensor,
        price_pred: torch.Tensor,
        price_true: torch.Tensor,
    ) -> torch.Tensor:
        direction_loss = self.ce_loss(direction_pred, direction_true)
        price_loss = self.mse_loss(price_pred, price_true)
        
        total_loss = self.direction_weight * direction_loss + self.price_weight * price_loss
        return total_loss, direction_loss, price_loss


async def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    device: torch.device,
    num_epochs: int,
    learning_rate: float,
    checkpoint_path: str,
) -> dict:
    """
    Обучение модели.
    
    Returns:
        Словарь с историей обучения
    """
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    criterion = CombinedLoss()
    
    best_val_loss = float("inf")
    patience_counter = 0
    history = {
        "train_loss": [],
        "val_loss": [],
        "val_metrics": [],
    }
    
    for epoch in range(num_epochs):
        # Training
        model.train()
        train_losses = []
        train_direction_losses = []
        train_price_losses = []
        
        for batch in train_loader:
            x = batch["features"].to(device)
            direction_true = batch["direction"].to(device)
            price_true = batch["price"].to(device)
            
            optimizer.zero_grad()
            output = model(x)
            
            total_loss, direction_loss, price_loss = criterion(
                output["direction"],
                direction_true,
                output["price"],
                price_true,
            )
            
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            
            train_losses.append(total_loss.item())
            train_direction_losses.append(direction_loss.item())
            train_price_losses.append(price_loss.item())
        
        # Validation
        model.eval()
        val_losses = []
        
        with torch.no_grad():
            for batch in val_loader:
                x = batch["features"].to(device)
                direction_true = batch["direction"].to(device)
                price_true = batch["price"].to(device)
                
                output = model(x)
                total_loss, _, _ = criterion(
                    output["direction"],
                    direction_true,
                    output["price"],
                    price_true,
                )
                val_losses.append(total_loss.item())
        
        avg_train_loss = np.mean(train_losses)
        avg_val_loss = np.mean(val_losses)
        
        history["train_loss"].append(avg_train_loss)
        history["val_loss"].append(avg_val_loss)
        
        # Вычисляем метрики на валидации
        val_metrics = evaluate_model(model, val_loader, device)
        history["val_metrics"].append(val_metrics)
        
        print(
            f"Epoch {epoch+1}/{num_epochs} - "
            f"Train Loss: {avg_train_loss:.4f}, "
            f"Val Loss: {avg_val_loss:.4f}, "
            f"Val Accuracy: {val_metrics['accuracy']:.4f}, "
            f"Val MAE: {val_metrics['mae']:.4f}"
        )
        
        # Early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            
            # Сохраняем лучшую модель
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_loss": avg_val_loss,
                "val_metrics": val_metrics,
                "history": history,
            }, checkpoint_path)
            print(f"Saved checkpoint to {checkpoint_path}")
        else:
            patience_counter += 1
            if patience_counter >= EARLY_STOPPING_PATIENCE:
                print(f"Early stopping at epoch {epoch+1}")
                break
    
    return history


async def main():
    parser = argparse.ArgumentParser(description="Train Mamba Prediction Model")
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--db", default=None, help="PostgreSQL URL (optional)")
    parser.add_argument("--exchange", default="bybit", help="Exchange name")
    parser.add_argument("--symbol", default="BTCUSDT", help="Symbol")
    parser.add_argument("--checkpoint", default=None, help="Path to save checkpoint")
    parser.add_argument("--resume", default=None, help="Path to checkpoint to resume from")
    args = parser.parse_args()
    
    device = torch.device(DEVICE if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # Загрузка данных
    print("Loading data...")
    if args.db:
        features, directions, prices = await load_data_from_postgres(
            args.db,
            args.exchange,
            args.symbol,
            SEQUENCE_LENGTH,
        )
    else:
        features, directions, prices = await load_data_from_redis(
            args.redis,
            args.exchange,
            args.symbol,
            SEQUENCE_LENGTH,
        )
    
    if len(features) == 0:
        print("No data loaded. Exiting.")
        return
    
    print(f"Loaded {len(features)} samples")
    
    # Нормализация признаков
    from services.mamba_predictor.preprocessing.normalizer import FeatureNormalizer
    
    normalizer = FeatureNormalizer(method="standard")
    features_normalized = normalizer.fit_transform(features)
    
    # Создание dataset
    dataset = TradingDataset(features_normalized, directions, prices)
    
    # Разделение на train/val
    val_size = int(len(dataset) * VALIDATION_SPLIT)
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)
    
    # Создание модели
    model = MultiHeadMambaPredictor(
        input_features=INPUT_FEATURES,
        hidden_dim=HIDDEN_DIM,
        d_state=D_STATE,
        d_conv=D_CONV,
        expand=EXPAND,
    ).to(device)
    
    # Resume from checkpoint
    if args.resume and os.path.exists(args.resume):
        print(f"Resuming from {args.resume}")
        checkpoint = torch.load(args.resume, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
    
    # Обучение
    checkpoint_path = args.checkpoint or os.path.join(
        MODEL_CHECKPOINT_PATH,
        f"mamba_{args.exchange}_{args.symbol}.pt"
    )
    
    history = await train_model(
        model,
        train_loader,
        val_loader,
        device,
        NUM_EPOCHS,
        LEARNING_RATE,
        checkpoint_path,
    )
    
    print("Training completed!")
    print(f"Best checkpoint saved to: {checkpoint_path}")


if __name__ == "__main__":
    asyncio.run(main())
