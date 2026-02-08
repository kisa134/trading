from .tick_encoder import (
    build_tick_encoder,
    encode_tick_sequence,
    infer_signal,
)

__all__ = [
    "build_tick_encoder",
    "encode_tick_sequence",
    "infer_signal",
]

try:
    from .tick_encoder import TickEncoderLSTM
    __all__.append("TickEncoderLSTM")
except (ImportError, AttributeError):
    TickEncoderLSTM = None
