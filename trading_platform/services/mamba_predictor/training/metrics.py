"""
Metrics for model evaluation.
"""
import numpy as np
import torch
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, mean_absolute_error, mean_squared_error
from typing import Dict, Tuple


def calculate_direction_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Dict[str, float]:
    """
    Расчет метрик для классификации направления.
    
    Args:
        y_true: True labels (0 = short, 1 = long)
        y_pred: Predicted labels (0 = short, 1 = long)
    
    Returns:
        Словарь с метриками
    """
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, average="binary", zero_division=0)
    recall = recall_score(y_true, y_pred, average="binary", zero_division=0)
    f1 = f1_score(y_true, y_pred, average="binary", zero_division=0)
    
    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
    }


def calculate_price_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Dict[str, float]:
    """
    Расчет метрик для регрессии цены.
    
    Args:
        y_true: True prices
        y_pred: Predicted prices
    
    Returns:
        Словарь с метриками
    """
    mae = mean_absolute_error(y_true, y_pred)
    mse = mean_squared_error(y_true, y_pred)
    rmse = np.sqrt(mse)
    
    # MAPE (Mean Absolute Percentage Error)
    mape = np.mean(np.abs((y_true - y_pred) / (y_true + 1e-10))) * 100
    
    return {
        "mae": float(mae),
        "mse": float(mse),
        "rmse": float(rmse),
        "mape": float(mape),
    }


def calculate_combined_metrics(
    direction_true: np.ndarray,
    direction_pred: np.ndarray,
    price_true: np.ndarray,
    price_pred: np.ndarray,
) -> Dict[str, float]:
    """
    Расчет комбинированных метрик для multi-head модели.
    
    Returns:
        Словарь со всеми метриками
    """
    direction_metrics = calculate_direction_metrics(direction_true, direction_pred)
    price_metrics = calculate_price_metrics(price_true, price_pred)
    
    return {
        **direction_metrics,
        **price_metrics,
    }


def evaluate_model(
    model: torch.nn.Module,
    dataloader: torch.utils.data.DataLoader,
    device: torch.device,
) -> Dict[str, float]:
    """
    Оценка модели на датасете.
    
    Args:
        model: Модель для оценки
        dataloader: DataLoader с тестовыми данными
        device: Устройство (CPU/GPU)
    
    Returns:
        Словарь с метриками
    """
    model.eval()
    
    all_direction_true = []
    all_direction_pred = []
    all_price_true = []
    all_price_pred = []
    
    with torch.no_grad():
        for batch in dataloader:
            x = batch["features"].to(device)
            direction_true = batch["direction"].to(device)
            price_true = batch["price"].to(device)
            
            output = model(x)
            
            # Direction predictions
            direction_probs = output["direction"]
            direction_pred = torch.argmax(direction_probs, dim=1).cpu().numpy()
            direction_true_np = direction_true.cpu().numpy()
            
            # Price predictions
            price_pred = output["price"].cpu().numpy()
            price_true_np = price_true.cpu().numpy()
            
            all_direction_true.extend(direction_true_np)
            all_direction_pred.extend(direction_pred)
            all_price_true.extend(price_true_np)
            all_price_pred.extend(price_pred)
    
    # Преобразуем в numpy массивы
    direction_true_arr = np.array(all_direction_true)
    direction_pred_arr = np.array(all_direction_pred)
    price_true_arr = np.array(all_price_true)
    price_pred_arr = np.array(all_price_pred)
    
    # Рассчитываем метрики
    metrics = calculate_combined_metrics(
        direction_true_arr,
        direction_pred_arr,
        price_true_arr,
        price_pred_arr,
    )
    
    return metrics
