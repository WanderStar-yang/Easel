"""User confirmation and activation of a strategy recommendation (Phase 6)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from easel.social_operator.repository import AccountNotFoundError
from easel.social_operator.strategy_confirmation import StrategyConfirmationService

router = APIRouter(prefix="/api/operator/accounts/{account_id}", tags=["operator-strategy-confirmation"])


@lru_cache(maxsize=1)
def get_strategy_confirmation_service() -> StrategyConfirmationService:
    return StrategyConfirmationService()


class ConfirmedPillar(BaseModel):
    recommendation_pillar_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=600)
    allocation_ratio: int = Field(ge=0, le=100)


class ConfirmStrategy(BaseModel):
    recommendation_id: str = Field(min_length=1, max_length=100)
    positioning: str = Field(min_length=1, max_length=240)
    pillars: list[ConfirmedPillar] = Field(min_length=1, max_length=12)


@router.get("/active-strategy")
def get_active_strategy(account_id: str,
                        service: StrategyConfirmationService = Depends(get_strategy_confirmation_service)):
    try:
        return service.active(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc


@router.post("/strategy-confirmation", status_code=201)
def confirm_strategy(account_id: str, payload: ConfirmStrategy,
                     service: StrategyConfirmationService = Depends(get_strategy_confirmation_service)):
    try:
        return service.confirm(account_id, payload.model_dump())
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
