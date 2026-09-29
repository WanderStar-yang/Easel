"""Source adapters that normalize facts into the shared HistoricalPost contract."""

from __future__ import annotations

import os
from typing import Protocol


class HistoricalDataSourceAdapter(Protocol):
    source: str

    def adapt(self, records: list[dict]) -> list[dict]: ...


_FACT_FIELDS = (
    "platform_post_id", "title", "publish_time", "duration", "views", "likes", "comments",
    "favorites", "shares",
)


class DouyinCreatorCenterAdapter:
    """Map explicitly scanned, visible creator-center fields without classification."""

    source = "DOUYIN_CREATOR_CENTER"

    def adapt(self, records: list[dict]) -> list[dict]:
        adapted = []
        for record in records:
            row = {field: record.get(field) for field in _FACT_FIELDS}
            if row["views"] is None and "play_count" in record:
                row["views"] = record.get("play_count")
            # Deliberately do not infer content_type, content_source, subjects, or hook_type.
            adapted.append(row)
        return adapted


class DouyinOpenApiAdapter:
    """Configuration boundary for the official API; never fabricates API records."""

    source = "DOUYIN_OPEN_API"

    @staticmethod
    def configuration_status() -> dict[str, object]:
        missing = [name for name in ("DOUYIN_CLIENT_KEY", "DOUYIN_CLIENT_SECRET") if not os.environ.get(name)]
        permission_granted = os.environ.get("DOUYIN_VIDEO_PERMISSIONS_GRANTED", "").lower() in {"1", "true", "yes"}
        if not permission_granted:
            missing.append("DOUYIN_VIDEO_PERMISSIONS_GRANTED(video.list,video.data)")
        enabled = not missing
        return {
            "configured": enabled,
            "missing_configuration": missing,
            "required_permissions": ["video.list", "video.data"],
            "implementation_available": False,
            "message": "官方 OpenAPI 尚未接入真实授权调用，目前使用创作者中心辅助同步。",
        }

    def adapt(self, records: list[dict]) -> list[dict]:
        raise RuntimeError("尚未配置抖音开放平台权限；未调用官方接口，也不会伪造作品数据。")


class FileImportAdapter:
    source = "FILE_IMPORT"

    def adapt(self, records: list[dict]) -> list[dict]:
        return [dict(record) for record in records]


class ManualInputAdapter:
    source = "MANUAL"

    def adapt(self, records: list[dict]) -> list[dict]:
        return [dict(record) for record in records]
