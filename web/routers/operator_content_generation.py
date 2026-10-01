"""AI content drafts generated only from a user's selected Topic."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from easel.social_operator.content_generation import ContentGenerationService
from easel.social_operator.repository import AccountNotFoundError

router = APIRouter(prefix="/api/operator/accounts/{account_id}", tags=["operator-content-generation"])


@lru_cache(maxsize=1)
def get_content_generation_service() -> ContentGenerationService:
    return ContentGenerationService()


class UpdateDraft(BaseModel):
    content: dict[str, Any] = Field(min_length=1)


@router.get("/topics/{topic_id}/content-draft")
def get_content_draft(account_id: str, topic_id: str,
                      service: ContentGenerationService = Depends(get_content_generation_service)):
    try:
        return service.get(account_id, topic_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/topics/{topic_id}/content-draft/generate", status_code=201)
def generate_content_draft(account_id: str, topic_id: str,
                           service: ContentGenerationService = Depends(get_content_generation_service)):
    try:
        return service.generate(account_id, topic_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/topics/{topic_id}/content-draft")
def update_content_draft(account_id: str, topic_id: str, payload: UpdateDraft,
                         service: ContentGenerationService = Depends(get_content_generation_service)):
    try:
        return service.update(account_id, topic_id, payload.content)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运营账号不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
