"""
Tick Encoder: sequence of (price_delta, volume, side) -> prob_up, prob_down, delta_score.
CPU fallback: LSTM + linear head. Optional: Mamba SSM when available (use_mamba=True, GPU).
"""
from __future__ import annotations

import numpy as np
from typing import Any

# Optional torch for inference
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    nn = None  # type: ignore


DEFAULT_WINDOW = 64
FEAT_DIM = 3  # price_delta_norm, volume_norm, side_encoded


def _to_tensor(x: np.ndarray, device: str = "cpu") -> Any:
    if not TORCH_AVAILABLE:
        return x
    return torch.from_numpy(x).float().to(device)


if TORCH_AVAILABLE:

    class TickEncoderLSTM(nn.Module):
        """LSTM-based tick sequence encoder. Outputs logits for up/down and delta_score."""

        def __init__(
            self,
            input_size: int = FEAT_DIM,
            hidden_size: int = 32,
            num_layers: int = 1,
            dropout: float = 0.0,
        ):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0,
            )
            self.head = nn.Linear(hidden_size, 3)  # prob_up, prob_down, delta_score (raw)

        def forward(self, x: Any) -> Any:
            out, _ = self.lstm(x)
            last = out[:, -1, :]
            return self.head(last)
else:
    TickEncoderLSTM = None  # type: ignore


def build_tick_encoder(use_mamba: bool = False, **kwargs: Any) -> Any:
    """Build encoder. use_mamba=True requires mamba-ssm (GPU). Default: LSTM CPU."""
    if use_mamba:
        try:
            from .mamba_encoder import TickEncoderMamba  # type: ignore
            return TickEncoderMamba(**kwargs)
        except ImportError:
            pass
    if not TORCH_AVAILABLE or TickEncoderLSTM is None:
        return None
    return TickEncoderLSTM(**kwargs)


def encode_tick_sequence(
    ticks: list[dict],
    window: int = DEFAULT_WINDOW,
    prev_price: float | None = None,
) -> np.ndarray:
    """
    Convert list of {price, size, side} into (window, FEAT_DIM) array.
    Features: price_delta (normalized), volume (log-normalized), side (1=buy, 0=sell).
    """
    if not ticks:
        return np.zeros((window, FEAT_DIM), dtype=np.float32)
    arr = []
    last_p = prev_price if prev_price is not None else float(ticks[0].get("price", 0))
    volumes = [float(t.get("size", t.get("volume", 0))) for t in ticks]
    vol_scale = np.log1p(max(volumes)) if volumes else 1.0
    for t in ticks[-window:]:
        p = float(t.get("price", 0))
        delta = (p - last_p) / (last_p + 1e-12)
        last_p = p
        vol = float(t.get("size", t.get("volume", 0)))
        vol_norm = np.log1p(vol) / (vol_scale + 1e-12)
        side = 1.0 if (str(t.get("side", "")).lower().startswith("b")) else 0.0
        arr.append([delta, vol_norm, side])
    arr = np.array(arr, dtype=np.float32)
    if len(arr) < window:
        pad = np.zeros((window - len(arr), FEAT_DIM), dtype=np.float32)
        arr = np.concatenate([pad, arr], axis=0)
    return arr


def infer_signal(
    encoder: Any,
    ticks: list[dict],
    window: int = DEFAULT_WINDOW,
    device: str = "cpu",
) -> dict[str, float]:
    """
    Run encoder on tick window. Returns {prob_up, prob_down, delta_score, ts}.
    If encoder is None or inference fails, returns heuristic from recent delta.
    """
    ts = ticks[-1].get("ts", 0) if ticks else 0
    if encoder is None or not TORCH_AVAILABLE:
        return _heuristic_signal(ticks, ts)
    try:
        enc = encode_tick_sequence(ticks, window=window)
        enc_batch = enc[np.newaxis, :, :]
        x = _to_tensor(enc_batch, device)
        encoder.eval()
        with torch.no_grad():
            out = encoder(x)
        out = out.cpu().numpy()[0]
        prob_up = float(1.0 / (1.0 + np.exp(-out[0])))
        prob_down = float(1.0 / (1.0 + np.exp(-out[1])))
        delta_score = float(out[2])
        return {"prob_up": prob_up, "prob_down": prob_down, "delta_score": delta_score, "ts": ts}
    except Exception:
        return _heuristic_signal(ticks, ts)


def _heuristic_signal(ticks: list[dict], ts: int) -> dict[str, float]:
    """Rule-based: delta from recent buy/sell volume."""
    if len(ticks) < 2:
        return {"prob_up": 0.5, "prob_down": 0.5, "delta_score": 0.0, "ts": ts}
    buy_vol = sum(
        float(t.get("size", t.get("volume", 0)))
        for t in ticks[-50:]
        if str(t.get("side", "")).lower().startswith("b")
    )
    sell_vol = sum(
        float(t.get("size", t.get("volume", 0)))
        for t in ticks[-50:]
        if not str(t.get("side", "")).lower().startswith("b")
    )
    total = buy_vol + sell_vol
    if total <= 0:
        return {"prob_up": 0.5, "prob_down": 0.5, "delta_score": 0.0, "ts": ts}
    delta_score = (buy_vol - sell_vol) / total
    prob_up = 0.5 + 0.5 * min(1, max(-1, delta_score))
    prob_down = 1.0 - prob_up
    return {"prob_up": prob_up, "prob_down": prob_down, "delta_score": delta_score, "ts": ts}
