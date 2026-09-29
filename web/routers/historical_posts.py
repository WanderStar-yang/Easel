"""Account-scoped HistoricalPost CRUD, import, and completeness APIs."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from easel.social_operator.historical import (
    DuplicateHistoricalPostError,
    HistoricalPostService,
    InvalidHistoricalPostError,
)
from easel.social_operator.historical_imports import MAX_IMPORT_BYTES, HistoricalImportManager
from easel.social_operator.models import ContentSource
from easel.social_operator.repository import AccountNotFoundError, OperatorAccountRepository
from easel.social_operator.service import OperatorAccountService

router = APIRouter(prefix="/api/operator/accounts/{account_id}/posts", tags=["historical-posts"])


@dataclass
class HistoricalServices:
    accounts: OperatorAccountService
    posts: HistoricalPostService
    imports: HistoricalImportManager


@lru_cache(maxsize=1)
def get_historical_services() -> HistoricalServices:
    repository = OperatorAccountRepository()
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    return HistoricalServices(accounts, posts, HistoricalImportManager(posts, repository))


class _PostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publish_time: str | None = None
    title: str = Field(min_length=1, max_length=1000)
    content_type: str | None = None
    content_source: ContentSource = ContentSource.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    duration: float | None = Field(default=None, ge=0)
    subjects: list[str] = Field(default_factory=list)
    hook_type: str | None = None
    views: int | None = Field(default=None, ge=0)
    exposure: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_gain: int | None = None
    profile_visits: int | None = Field(default=None, ge=0)
    inquiries: int | None = Field(default=None, ge=0)
    platform_post_id: str | None = None


class PostCreate(_PostModel):
    pass


class PostUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publish_time: str | None = None
    title: str | None = Field(default=None, max_length=1000)
    content_type: str | None = None
    content_source: ContentSource | None = None
    tags: list[str] | None = None
    note: str | None = None
    duration: float | None = Field(default=None, ge=0)
    subjects: list[str] | None = None
    hook_type: str | None = None
    views: int | None = Field(default=None, ge=0)
    exposure: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    followers_gain: int | None = None
    profile_visits: int | None = Field(default=None, ge=0)
    inquiries: int | None = Field(default=None, ge=0)
    platform_post_id: str | None = None


def _account(services: HistoricalServices, account_id: str) -> None:
    try:
        services.accounts.get_account(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operator account not found") from exc


def _raise_post_error(exc: Exception) -> None:
    if isinstance(exc, InvalidHistoricalPostError):
        raise HTTPException(status_code=422, detail={"message": str(exc), "fields": exc.errors}) from exc
    if isinstance(exc, DuplicateHistoricalPostError):
        raise HTTPException(status_code=409, detail={"message": str(exc), "duplicate_id": exc.duplicate_id}) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail="Historical post not found") from exc
    raise exc


@router.get("")
def list_posts(
    account_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    services: HistoricalServices = Depends(get_historical_services),
):
    _account(services, account_id)
    rows = services.posts.list_posts(account_id, offset=offset, limit=limit)
    return {"items": [row.as_dict() for row in rows], "offset": offset, "limit": limit,
            "total": services.posts.repository.count_posts(account_id)}


@router.get("/completeness")
def get_completeness(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    return services.posts.completeness(account_id)


@router.post("", status_code=201)
def create_post(account_id: str, payload: PostCreate,
                services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return services.posts.create_post(account_id, payload.model_dump()).as_dict()
    except Exception as exc:
        _raise_post_error(exc)


@router.get("/{post_id}")
def get_post(account_id: str, post_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return services.posts.get_post(account_id, post_id).as_dict()
    except LookupError as exc:
        _raise_post_error(exc)


@router.patch("/{post_id}")
def update_post(account_id: str, post_id: str, payload: PostUpdate,
                services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return services.posts.update_post(account_id, post_id, payload.model_dump(exclude_unset=True)).as_dict()
    except Exception as exc:
        _raise_post_error(exc)


@router.delete("/{post_id}")
def delete_post(account_id: str, post_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        services.posts.delete_post(account_id, post_id)
    except LookupError as exc:
        _raise_post_error(exc)
    return {"deleted": True, "id": post_id}


@router.post("/imports/preview")
async def preview_import(account_id: str, file: UploadFile = File(...),
                        services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    # Read only one byte past the configured cap so an oversized upload cannot
    # consume unbounded memory before the import service rejects it.
    content = await file.read(MAX_IMPORT_BYTES + 1)
    try:
        preview_id, summary = services.imports.preview(account_id, file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"preview_id": preview_id, **summary}


class ImportConfirm(BaseModel):
    preview_id: str


@router.post("/imports/confirm")
def confirm_import(account_id: str, payload: ImportConfirm,
                   services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return services.imports.confirm(account_id, payload.preview_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="导入预览不存在、已失效或不属于当前账号") from exc
