"""Account-scoped Social Operator calendar APIs."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from easel.social_operator.content_calendar import OperatorContentCalendarService
from easel.social_operator.repository import AccountNotFoundError

router = APIRouter(prefix="/api/operator/accounts/{account_id}/calendar", tags=["operator-calendar"])


@lru_cache(maxsize=1)
def get_service() -> OperatorContentCalendarService:
    return OperatorContentCalendarService()


class CalendarPlanInput(BaseModel):
    topic_id: str = Field(min_length=1, max_length=120)
    draft_id: str | None = Field(default=None, max_length=120)
    planned_publish_at: str = Field(min_length=16, max_length=64)


class RescheduleInput(BaseModel):
    planned_publish_at: str = Field(min_length=16, max_length=64)


class PublishInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    published_at: str = Field(min_length=16, max_length=64)
    platform_post_id: str | None = Field(default=None, max_length=200)
    published_url: str | None = Field(default=None, max_length=2000)
    content_source: Literal["REAL", "AI", "MIXED", "UNKNOWN"] = "UNKNOWN"
    hook_type: str | None = Field(default=None, max_length=120)
    duration_seconds: int | None = Field(default=None, ge=1, le=3600)


def _not_found(exc: AccountNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="运营账号不存在。")


def _conflict(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("")
def calendar_context(account_id: str, start: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
                     end: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
                     service: OperatorContentCalendarService = Depends(get_service)):
    try:
        return service.context(account_id, start, end)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _conflict(exc) from exc


@router.post("", status_code=201)
def schedule_topic(account_id: str, payload: CalendarPlanInput,
                   service: OperatorContentCalendarService = Depends(get_service)):
    try:
        return service.schedule(account_id, payload.topic_id, payload.draft_id, payload.planned_publish_at)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _conflict(exc) from exc


@router.put("/{item_id}/date")
def reschedule_topic(account_id: str, item_id: str, payload: RescheduleInput,
                     service: OperatorContentCalendarService = Depends(get_service)):
    try:
        return service.reschedule(account_id, item_id, payload.planned_publish_at)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _conflict(exc) from exc


@router.post("/{item_id}/ready")
def mark_ready(account_id: str, item_id: str, service: OperatorContentCalendarService = Depends(get_service)):
    try:
        return service.mark_ready(account_id, item_id)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _conflict(exc) from exc


@router.post("/{item_id}/cancel")
def cancel_plan(account_id: str, item_id: str, service: OperatorContentCalendarService = Depends(get_service)):
    try:
        return service.cancel(account_id, item_id)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _conflict(exc) from exc


@router.post("/{item_id}/publish")
def record_actual_publication(account_id: str, item_id: str, payload: PublishInput,
                              service: OperatorContentCalendarService = Depends(get_service)):
    try:
        return service.mark_published(account_id, item_id, payload.model_dump())
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _conflict(exc) from exc
