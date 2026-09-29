"""API routes for Social Operator business accounts (separate from login accounts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from easel.social_operator import AccountStatus, OperatorAccount, OperatorAccountService, Platform
from easel.social_operator.repository import AccountNotFoundError, DuplicatePlatformError
from easel.social_operator.service import InvalidProfileReferenceError, InvalidTransitionError

router = APIRouter(prefix="/api/operator/accounts", tags=["operator-accounts"])


def get_service() -> OperatorAccountService:
    return OperatorAccountService()


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: Platform
    profileSummary: str = ""
    strategySummary: str = ""


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: AccountStatus | None = None
    profileSummary: str | None = None
    easelProfileName: str | None = None
    strategySummary: str | None = None

    @model_validator(mode="after")
    def reject_null_updates(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


def _serialize(account: OperatorAccount) -> dict:
    return account.as_dict()


@router.get("")
def list_operator_accounts(service: OperatorAccountService = Depends(get_service)):
    return [_serialize(account) for account in service.list_accounts()]


@router.post("", status_code=201)
def create_operator_account(payload: AccountCreate, service: OperatorAccountService = Depends(get_service)):
    try:
        account = service.create_account(
            name=payload.name, platform=payload.platform,
            profile_summary=payload.profileSummary, strategy_summary=payload.strategySummary,
        )
    except DuplicatePlatformError as exc:
        raise HTTPException(status_code=409, detail="An operator account already exists for this platform") from exc
    return _serialize(account)


@router.get("/{account_id}")
def get_operator_account(account_id: str, service: OperatorAccountService = Depends(get_service)):
    try:
        return _serialize(service.get_account(account_id))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operator account not found") from exc


@router.patch("/{account_id}")
def update_operator_account(account_id: str, payload: AccountUpdate,
                            service: OperatorAccountService = Depends(get_service)):
    try:
        return _serialize(service.update_account(account_id, payload.model_dump(exclude_unset=True)))
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operator account not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidProfileReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
