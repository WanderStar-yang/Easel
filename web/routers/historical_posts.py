"""Account-scoped HistoricalPost CRUD, import, and completeness APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from easel.social_operator.historical import (
    DuplicateHistoricalPostError,
    HistoricalPostService,
    InvalidHistoricalPostError,
)
from easel.social_operator.historical_imports import MAX_IMPORT_BYTES, HistoricalImportManager
from easel.social_operator.historical_sync import HistoricalSyncSessionManager
from easel.social_operator.data_sources import DouyinCreatorCenterAdapter, DouyinOpenApiAdapter
from easel.social_operator.models import ContentSource, Platform
from easel.social_operator.repository import AccountNotFoundError, OperatorAccountRepository
from easel.social_operator.snapshot_sync import SnapshotReconciliationManager
from easel.social_operator.service import OperatorAccountService

router = APIRouter(prefix="/api/operator/accounts/{account_id}/posts", tags=["historical-posts"])


@dataclass
class HistoricalServices:
    accounts: OperatorAccountService
    posts: HistoricalPostService
    imports: HistoricalImportManager
    sync_sessions: HistoricalSyncSessionManager = field(default_factory=HistoricalSyncSessionManager)
    snapshots: SnapshotReconciliationManager | None = None


@lru_cache(maxsize=1)
def get_historical_services() -> HistoricalServices:
    repository = OperatorAccountRepository()
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    return HistoricalServices(accounts, posts, HistoricalImportManager(posts, repository),
                              HistoricalSyncSessionManager(repository), SnapshotReconciliationManager(repository))


class _PostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publish_time: str | None = None
    publish_time_raw: str | None = None
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
    publish_time_raw: str | None = None
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


class SnapshotConfirm(BaseModel):
    preview_id: str


def _snapshots(services: HistoricalServices) -> SnapshotReconciliationManager:
    if services.snapshots is None:
        services.snapshots = SnapshotReconciliationManager(services.posts.repository)
    return services.snapshots


class CreatorCenterPreview(BaseModel):
    source_url: str
    records: list[dict] = Field(default_factory=list, max_length=5000)


class CreatorCenterCheckpoint(BaseModel):
    source_url: str
    page_fingerprint: str = Field(min_length=1, max_length=500)
    rows: list[dict] = Field(max_length=5000)
    has_next: bool = False
    next_page_hint: str = Field(default="", max_length=500)
    expected_count: int | None = Field(default=None, ge=0, le=100000)


class CreatorCenterControl(BaseModel):
    action: Literal["pause", "resume", "end", "cancel"]


class CreatorCenterExtensionState(BaseModel):
    status: Literal[
        "extension_available", "creator_tab_not_found", "not_logged_in", "unsupported_page",
        "ready_to_scan", "scanning", "paused", "scan_completed", "scan_failed", "ended", "cancelled",
    ]
    message: str = Field(default="", max_length=300)
    source_url: str = ""


@router.get("/sync/status")
def get_sync_status(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    return services.posts.repository.get_sync_status(account_id)


@router.get("/sync/openapi-status")
def get_openapi_status(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    account = services.accounts.get_account(account_id)
    if account.platform != Platform.DOUYIN:
        raise HTTPException(status_code=409, detail="官方数据采集入口仅适用于抖音账号")
    return DouyinOpenApiAdapter.configuration_status()


@router.post("/sync/sessions", status_code=201)
def create_sync_session(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    account = services.accounts.get_account(account_id)
    if account.platform != Platform.DOUYIN:
        raise HTTPException(status_code=409, detail="创作者中心辅助同步仅适用于抖音账号")
    return services.sync_sessions.create(account_id)


@router.get("/sync/sessions")
def list_sync_sessions(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    return {"items": services.sync_sessions.list(account_id)}


@router.post("/sync/sessions/{session_id}/extension-state")
def report_extension_state(account_id: str, session_id: str, payload: CreatorCenterExtensionState,
                           services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    account = services.accounts.get_account(account_id)
    if account.platform != Platform.DOUYIN:
        raise HTTPException(status_code=409, detail="创作者中心辅助同步仅适用于抖音账号")
    try:
        return services.sync_sessions.report_state(
            account_id, session_id, payload.status, payload.message, payload.source_url,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="同步会话不存在、已过期或不属于当前账号") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sync/sessions/{session_id}")
def get_sync_session(account_id: str, session_id: str,
                     services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return services.sync_sessions.get(account_id, session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="同步会话不存在、已过期或不属于当前账号") from exc


@router.post("/sync/sessions/{session_id}/control")
def control_sync_session(account_id: str, session_id: str, payload: CreatorCenterControl,
                         services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return services.sync_sessions.control(account_id, session_id, payload.action)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="同步会话不存在、已过期或不属于当前账号") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sync/sessions/{session_id}/checkpoint")
def checkpoint_creator_center_scan(account_id: str, session_id: str, payload: CreatorCenterCheckpoint,
                                   services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    account = services.accounts.get_account(account_id)
    if account.platform != Platform.DOUYIN:
        raise HTTPException(status_code=409, detail="创作者中心辅助同步仅适用于抖音账号")
    try:
        return services.sync_sessions.checkpoint(
            account_id, session_id, payload.rows, payload.source_url,
            page_fingerprint=payload.page_fingerprint, has_next=payload.has_next,
            next_page_hint=payload.next_page_hint, expected_count=payload.expected_count,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="同步会话不存在、已过期或不属于当前账号") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sync/sessions/{session_id}/preview", status_code=201)
def preview_creator_center_sync(account_id: str, session_id: str, payload: CreatorCenterPreview,
                                services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    account = services.accounts.get_account(account_id)
    if account.platform != Platform.DOUYIN:
        raise HTTPException(status_code=409, detail="创作者中心辅助同步仅适用于抖音账号")
    if not services.sync_sessions.validate_creator_center_url(payload.source_url):
        raise HTTPException(status_code=403, detail="只接受从抖音创作者中心页面主动扫描的数据")
    try:
        # A Snapshot is the session's accumulated, deduplicated full scan. Ignore any
        # client-side row payload so confirmation cannot reconcile a partial/different set.
        records = services.sync_sessions.preview_records(account_id, session_id)
        session_status = services.sync_sessions.get(account_id, session_id)
        if session_status["status"] not in {"scan_completed", "ended"}:
            raise HTTPException(status_code=409, detail="请先完成扫描或结束当前扫描，再生成已保存内容的预览")
        adapter = DouyinCreatorCenterAdapter()
        summary = _snapshots(services).preview_snapshot(
            account_id, adapter.adapt(records), raw_count=session_status["raw_observation_count"],
            scan_duplicate_count=session_status["duplicate_count"], pages_scanned=session_status["pages_scanned"],
            expected_count=session_status.get("expected_count"),
            scan_complete=session_status["status"] == "scan_completed",
        )
        return services.sync_sessions.attach_preview(
            account_id, session_id, summary["preview_id"], summary, payload.source_url,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="同步会话不存在、已过期或不属于当前账号") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/sync/snapshots/confirm")
def confirm_creator_center_snapshot(account_id: str, payload: SnapshotConfirm,
                                    services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return _snapshots(services).confirm(account_id, payload.preview_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="快照预览不存在、已过期或不属于当前账号") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/repair/preview")
def preview_historical_repair(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return _snapshots(services).preview_repair(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/repair/confirm")
def confirm_historical_repair(account_id: str, payload: SnapshotConfirm,
                              services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return _snapshots(services).confirm_repair(account_id, payload.preview_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="修复预览不存在、已过期或不属于当前账号") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/imports/confirm")
def confirm_import(account_id: str, payload: ImportConfirm,
                   services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return services.imports.confirm(account_id, payload.preview_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="导入预览不存在、已失效或不属于当前账号") from exc
