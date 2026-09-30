"""Account-scoped historical baseline API."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from easel.social_operator.baselines import AccountBaselineService
from easel.social_operator.repository import AccountNotFoundError

router = APIRouter(prefix="/api/operator/accounts/{account_id}/baseline", tags=["operator-baseline"])


@lru_cache(maxsize=1)
def get_baseline_service() -> AccountBaselineService:
    return AccountBaselineService()


class GenerateBaseline(BaseModel):
    historical_data_version: str = Field(min_length=32, max_length=128)


class CompareMetrics(BaseModel):
    metrics: dict[str, int | float | None]


@router.get("")
def latest_baseline(account_id: str, service: AccountBaselineService = Depends(get_baseline_service)):
    try:
        baseline = service.latest(account_id)
        return baseline.as_dict() if baseline else None
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc


@router.get("/history")
def baseline_history(account_id: str, service: AccountBaselineService = Depends(get_baseline_service)):
    try:
        return [baseline.as_dict() for baseline in service.history(account_id)]
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc


@router.post("/preview")
def preview_baseline(account_id: str, service: AccountBaselineService = Depends(get_baseline_service)):
    try:
        return service.preview(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("")
def generate_baseline(account_id: str, payload: GenerateBaseline,
                      service: AccountBaselineService = Depends(get_baseline_service)):
    try:
        return service.generate(account_id, payload.historical_data_version).as_dict()
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/compare")
def compare_metrics(account_id: str, payload: CompareMetrics,
                    service: AccountBaselineService = Depends(get_baseline_service)):
    try:
        return service.compare_to_baseline(account_id, payload.metrics)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
