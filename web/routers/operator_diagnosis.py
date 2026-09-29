"""Account-scoped Initial Diagnosis API."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from easel.social_operator.diagnosis import (
    AccountDiagnosisService,
    DiagnosisStateError,
    InsufficientHistoryError,
    OpenClawDiagnosisExplainer,
)
from easel.social_operator.repository import AccountNotFoundError

router = APIRouter(prefix="/api/operator/accounts/{account_id}/diagnosis", tags=["operator-diagnosis"])


@lru_cache(maxsize=1)
def get_diagnosis_service() -> AccountDiagnosisService:
    return AccountDiagnosisService(explainer=OpenClawDiagnosisExplainer())


@router.post("")
def run_diagnosis(account_id: str,
                  service: AccountDiagnosisService = Depends(get_diagnosis_service)):
    try:
        return service.diagnose(account_id).as_dict()
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except DiagnosisStateError as exc:
        raise HTTPException(status_code=409, detail={"code": "INVALID_ACCOUNT_STATE", "message": str(exc)}) from exc
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operator account not found") from exc


@router.get("")
def get_latest_diagnosis(account_id: str,
                         service: AccountDiagnosisService = Depends(get_diagnosis_service)):
    try:
        return service.get_latest(account_id).as_dict()
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operator account not found") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Initial diagnosis not found") from exc


@router.get("/history")
def get_diagnosis_history(account_id: str, limit: int = Query(default=20, ge=1, le=100),
                          service: AccountDiagnosisService = Depends(get_diagnosis_service)):
    try:
        return [item.as_dict() for item in service.list_history(account_id, limit=limit)]
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operator account not found") from exc
