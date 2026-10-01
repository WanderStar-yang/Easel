"""Daily topic recommendation and selection for ACTIVE Social Operator accounts."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from easel.social_operator.repository import AccountNotFoundError
from easel.social_operator.topic_recommendations import TopicRecommendationService

router = APIRouter(prefix="/api/operator/accounts/{account_id}/daily-topics",
                   tags=["operator-daily-topics"])


@lru_cache(maxsize=1)
def get_topic_service() -> TopicRecommendationService:
    return TopicRecommendationService()


@router.get("")
def get_today_topics(account_id: str,
                     service: TopicRecommendationService = Depends(get_topic_service)):
    try:
        return service.today(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("")
def generate_today_topics(account_id: str,
                          service: TopicRecommendationService = Depends(get_topic_service)):
    try:
        return service.generate(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{topic_id}/select")
def select_today_topic(account_id: str, topic_id: str,
                       service: TopicRecommendationService = Depends(get_topic_service)):
    try:
        return service.select(account_id, topic_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
