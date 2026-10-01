"""Explicit generation and history for Phase 5 strategy recommendations."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from easel.social_operator.repository import AccountNotFoundError
from easel.social_operator.strategy_recommendations import StrategyRecommendationService

router = APIRouter(prefix="/api/operator/accounts/{account_id}/strategy-recommendations",
                   tags=["operator-strategy-recommendations"])


@lru_cache(maxsize=1)
def get_strategy_recommendation_service() -> StrategyRecommendationService:
    return StrategyRecommendationService()


@router.get("")
def latest(account_id: str, service: StrategyRecommendationService = Depends(get_strategy_recommendation_service)):
    try:
        return service.latest(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc


@router.get("/history")
def history(account_id: str, service: StrategyRecommendationService = Depends(get_strategy_recommendation_service)):
    try:
        return service.history(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc


@router.post("")
def generate(account_id: str, service: StrategyRecommendationService = Depends(get_strategy_recommendation_service)):
    try:
        return service.generate(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
