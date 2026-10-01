"""Manual publication metrics, weekly review, and review-confirmed strategy memory APIs."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from easel.social_operator.feedback_repository import OperatorFeedbackRepository
from easel.social_operator.repository import AccountNotFoundError, OperatorAccountRepository
from easel.social_operator.weekly_review import METRIC_FIELDS, WeeklyReviewService

router = APIRouter(prefix="/api/operator/accounts/{account_id}", tags=["operator-feedback"])


@lru_cache(maxsize=1)
def get_service() -> WeeklyReviewService:
    return WeeklyReviewService()


class PublishedPostInput(BaseModel):
    topic_id: str = Field(min_length=1, max_length=120)
    draft_id: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    published_url: str | None = Field(default=None, max_length=2000)
    platform_post_id: str | None = Field(default=None, max_length=200)
    published_at: str = Field(min_length=10, max_length=64)
    content_source: Literal["REAL", "AI", "MIXED", "UNKNOWN"] = "UNKNOWN"
    hook_type: str | None = Field(default=None, max_length=120)
    duration_seconds: int | None = Field(default=None, ge=1, le=3600)


class MetricsInput(BaseModel):
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_gain: int | None = None
    profile_visits: int | None = Field(default=None, ge=0)
    inquiries: int | None = Field(default=None, ge=0)


class ReviewInput(BaseModel):
    week_start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class MemoryConfirmation(BaseModel):
    statement: str | None = Field(default=None, max_length=1000)


def _not_found(exc: AccountNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="运营账号不存在。")


@router.get("/feedback/context")
def feedback_context(account_id: str, service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.context(account_id)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/published-posts")
def list_published_posts(account_id: str, service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.feedback.list_posts(account_id)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/published-posts", status_code=201)
def register_published_post(account_id: str, payload: PublishedPostInput,
                            service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.register_published_post(account_id, topic_id=payload.topic_id, draft_id=payload.draft_id,
                                              values=payload.model_dump(exclude={"topic_id", "draft_id"}))
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/published-posts/{post_id}/metrics/{checkpoint}")
def record_metrics(account_id: str, post_id: str, checkpoint: Literal["24H", "72H", "7D"],
                   payload: MetricsInput, service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.record_metrics(account_id, post_id, checkpoint, payload.model_dump())
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/weekly-reviews")
def list_weekly_reviews(account_id: str, service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.list_reviews(account_id)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/weekly-reviews", status_code=201)
def create_weekly_review(account_id: str, payload: ReviewInput,
                         service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.generate(account_id, payload.week_start)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/weekly-reviews/{review_id}")
def get_weekly_review(account_id: str, review_id: str, service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.get_review(account_id, review_id)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/strategy-memories")
def list_strategy_memories(account_id: str, status: Literal["PROPOSED", "ACTIVE", "SUPERSEDED", "DISMISSED", "STALE"] | None = Query(default=None),
                           service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.list_memories(account_id, status)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/strategy-memories/{memory_id}/confirm")
def confirm_strategy_memory(account_id: str, memory_id: str, payload: MemoryConfirmation,
                            service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.decide_memory(account_id, memory_id, confirm=True, statement=payload.statement)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/strategy-memories/{memory_id}/dismiss")
def dismiss_strategy_memory(account_id: str, memory_id: str, service: WeeklyReviewService = Depends(get_service)):
    try:
        return service.decide_memory(account_id, memory_id, confirm=False)
    except AccountNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
