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
from easel.social_operator.douyin_export import DouyinCreatorExportParser
from easel.social_operator.classification import (
    ClassificationUnavailable, HistoricalClassificationService,
)
from easel.social_operator.models import ContentSource
from easel.social_operator.repository import AccountNotFoundError, OperatorAccountRepository
from easel.social_operator.snapshot_reconciliation import SnapshotReconciliationManager
from easel.social_operator.service import OperatorAccountService

router = APIRouter(prefix="/api/operator/accounts/{account_id}/posts", tags=["historical-posts"])


@dataclass
class HistoricalServices:
    accounts: OperatorAccountService
    posts: HistoricalPostService
    imports: HistoricalImportManager
    snapshots: SnapshotReconciliationManager | None = None
    classification: HistoricalClassificationService | None = None


@lru_cache(maxsize=1)
def get_historical_services() -> HistoricalServices:
    repository = OperatorAccountRepository()
    accounts = OperatorAccountService(repository)
    posts = HistoricalPostService(repository)
    return HistoricalServices(accounts, posts, HistoricalImportManager(posts, repository),
                              SnapshotReconciliationManager(repository),
                              HistoricalClassificationService(repository))


class _PostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publish_time: str | None = None
    publish_time_raw: str | None = None
    title: str = Field(min_length=1, max_length=1000)
    content_type: str | None = None
    content_type_raw: str | None = None
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
    content_type_raw: str | None = None
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


class BatchClassify(BaseModel):
    post_ids: list[str] = Field(min_length=1, max_length=500)
    content_source: ContentSource | None = None
    content_type: str | None = Field(default=None, max_length=120)
    subjects: list[str] | None = Field(default=None, max_length=10)


class AcceptSuggestions(BaseModel):
    post_ids: list[str] = Field(min_length=1, max_length=500)
    fields: list[str] = Field(min_length=1, max_length=3)
    high_confidence_only: bool = False


class SuggestRequest(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=3)


def _account(services: HistoricalServices, account_id: str) -> None:
    try:
        services.accounts.get_account(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operator account not found") from exc


def _classification(services: HistoricalServices) -> HistoricalClassificationService:
    if services.classification is None:
        services.classification = HistoricalClassificationService(services.posts.repository)
    return services.classification


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
            "total": services.posts.canonical_count(account_id),
            "raw_total": services.posts.repository.count_posts(account_id)}


@router.get("/completeness")
def get_completeness(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    return services.posts.completeness(account_id)


@router.get("/classification/progress")
def classification_progress(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    return _classification(services).progress(account_id)


@router.get("/classification/runtime")
def classification_runtime(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    return _classification(services).runtime_status().as_dict()


@router.get("/classification/rows")
def classification_rows(account_id: str, services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    return {"items": _classification(services).classification_rows(account_id)}


@router.post("/classification/ai-suggest")
def suggest_classifications(account_id: str, payload: SuggestRequest | None = None,
                            services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    status = _classification(services).runtime_status()
    if status.state.value == "NOT_CONFIGURED":
        raise HTTPException(status_code=409, detail="尚未配置 AI 模型，请先完成模型设置。")
    if status.state.value == "UNAVAILABLE":
        raise HTTPException(status_code=503, detail="当前 AI 服务暂时不可用。")
    if status.state.value == "ERROR":
        raise HTTPException(status_code=502, detail="AI 模型配置或连接发生错误，请检查模型设置。")
    try:
        return _classification(services).suggest(account_id, payload.fields if payload else None)
    except ClassificationUnavailable as exc:
        raise HTTPException(status_code=503, detail="当前 AI 服务暂时不可用。") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="账号不存在") from exc


@router.post("/classification/suggestions/accept")
def accept_suggestions(account_id: str, payload: AcceptSuggestions,
                       services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return _classification(services).accept(account_id, payload.post_ids, payload.fields,
                                                high_confidence_only=payload.high_confidence_only)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


@router.patch("/batch-classify")
def batch_classify(account_id: str, payload: BatchClassify,
                   services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    values = {key: value for key, value in payload.model_dump(exclude_unset=True).items()
              if key != "post_ids" and value is not None}
    try:
        return {"updated_count": services.posts.classify_posts(account_id, payload.post_ids, values)}
    except (InvalidHistoricalPostError, LookupError, ValueError) as exc:
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
        if len(content) > MAX_IMPORT_BYTES:
            raise ValueError("文件不能超过 10 MB")
        filename = file.filename or ""
        parsed = DouyinCreatorExportParser().parse_file(filename, content)
        if parsed is not None:
            summary = _snapshots(services).preview_snapshot(
                account_id, parsed.records, headers=parsed.headers,
                unsupported_columns=parsed.unsupported_columns,
                missing_columns=sorted({"publish_time", "content_type_raw", "views", "likes", "comments", "favorites"}
                                       - DouyinCreatorExportParser.mapped_fields(parsed.headers)),
            )
            return summary
        preview_id, summary = services.imports.preview(account_id, filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"preview_id": preview_id, **summary}


class ImportConfirm(BaseModel):
    preview_id: str


class SnapshotConfirm(BaseModel):
    preview_id: str
    manual_group_ids: list[str] = Field(default_factory=list, max_length=200)


def _snapshots(services: HistoricalServices) -> SnapshotReconciliationManager:
    if services.snapshots is None:
        services.snapshots = SnapshotReconciliationManager(services.posts.repository)
    return services.snapshots


@router.post("/imports/snapshot-confirm")
def confirm_official_export_snapshot(account_id: str, payload: SnapshotConfirm,
                                     services: HistoricalServices = Depends(get_historical_services)):
    _account(services, account_id)
    try:
        return _snapshots(services).confirm(account_id, payload.preview_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="官方导出预览不存在、已过期或不属于当前账号") from exc
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
        return _snapshots(services).confirm_repair(account_id, payload.preview_id, payload.manual_group_ids)
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
