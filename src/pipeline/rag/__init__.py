"""
RAG 파이프라인 공개 API.

사용 예:
    from src.pipeline.rag import predict_and_save, load_prediction, PredictionOutput
    from src.pipeline.rag import snapshot as rag_snap
"""
from src.pipeline.rag.models import PredictionOutput
from src.pipeline.rag.predictor import predict_and_save, load_prediction

__all__ = [
    "PredictionOutput",
    "predict_and_save",
    "load_prediction",
]
