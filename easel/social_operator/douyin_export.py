"""Parser for PC Douyin Creator Center's exported work-list spreadsheets."""

from __future__ import annotations

from dataclasses import dataclass

from .historical_imports import _normalize_header, read_import_file


_ALIASES = {
    "作品名称": "title", "作品标题": "title", "标题": "title",
    "发布时间": "publish_time", "发布日期": "publish_time", "publishtime": "publish_time",
    "体裁": "content_type_raw", "作品类型": "content_type_raw",
    "作品id": "platform_post_id", "内容id": "platform_post_id", "视频id": "platform_post_id",
    "播放量": "views", "播放": "views", "浏览量": "views", "曝光量": "views", "曝光": "views",
    "点赞量": "likes", "点赞": "likes",
    "评论量": "comments", "评论": "comments",
    "收藏量": "favorites", "收藏": "favorites",
    "分享量": "shares", "分享": "shares",
    "粉丝增量": "followers_gain", "吸粉量": "followers_gain", "新增粉丝": "followers_gain", "涨粉": "followers_gain",
    "主页访问量": "profile_visits", "主页访问": "profile_visits",
}

_SIGNATURE_FIELDS = {"作品名称", "发布时间", "播放量", "点赞量", "评论量", "收藏量", "分享量", "粉丝增量"}


@dataclass(frozen=True)
class DouyinCreatorExport:
    records: list[dict]
    headers: list[str]
    unsupported_columns: list[str]


class DouyinCreatorExportParser:
    """Recognize and map official work-list exports without rejecting extra metrics."""

    source = "DOUYIN_OFFICIAL_EXPORT"

    @staticmethod
    def recognizes(headers: list[str]) -> bool:
        normalized = {_normalize_header(header) for header in headers}
        # A Douyin export has its platform-specific work-name column and at least
        # one companion platform metric/header. This avoids treating every XLSX
        # with a generic title column as an official snapshot.
        return "作品名称" in normalized and bool((normalized & _SIGNATURE_FIELDS) - {"作品名称"})

    @staticmethod
    def mapped_fields(headers: list[str]) -> set[str]:
        return {_ALIASES[_normalize_header(header)] for header in headers if _normalize_header(header) in _ALIASES}

    @staticmethod
    def parse_rows(raw_rows: list[dict], headers: list[str]) -> DouyinCreatorExport:
        records: list[dict] = []
        for raw in raw_rows:
            mapped: dict = {}
            for header, value in raw.items():
                field = _ALIASES.get(_normalize_header(header))
                if field:
                    mapped[field] = value
            mapped["data_source"] = DouyinCreatorExportParser.source
            records.append(mapped)
        unsupported = [header for header in headers if _normalize_header(header) not in _ALIASES]
        return DouyinCreatorExport(records, headers, unsupported)

    def parse_file(self, filename: str, content: bytes) -> DouyinCreatorExport | None:
        if filename.rsplit(".", 1)[-1].lower() != "xlsx":
            return None
        raw_rows, headers = read_import_file(filename, content)
        if not self.recognizes(headers):
            return None
        return self.parse_rows(raw_rows, headers)
