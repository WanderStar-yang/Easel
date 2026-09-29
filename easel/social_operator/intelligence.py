"""Deterministic, account-scoped analysis shared by diagnosis and later reviews."""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from .models import Platform

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# Reuse Easel's tested pure-statistics helpers; no LLM computes facts.
import social_stats  # noqa: E402

ALGORITHM_VERSION = "account-intelligence-v1"
METRICS = (
    "views", "likes", "comments", "favorites", "shares", "followers_gain",
    "profile_visits", "inquiries",
)
INTERACTION_METRICS = ("likes", "comments", "favorites", "shares")
DOUYIN_METRICS = ("views", "likes", "comments", "favorites", "shares", "followers_gain")
XHS_METRICS = METRICS
CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def confidence_level(sample_size: int, completeness: float, metric_coverage: float) -> str:
    """Conservative report confidence; thresholds are versioned with the algorithm."""
    if sample_size >= 20 and completeness >= 80 and metric_coverage >= 0.7:
        return "HIGH"
    if sample_size >= 8 and completeness >= 50 and metric_coverage >= 0.4:
        return "MEDIUM"
    return "LOW"


def _group_confidence(sample_size: int, overall: str) -> str:
    group = "HIGH" if sample_size >= 15 else "MEDIUM" if sample_size >= 5 else "LOW"
    return min((group, overall), key=lambda level: CONFIDENCE_ORDER[level])


def _number_median(rows: list[dict], field: str) -> float | None:
    return social_stats.median([row.get(field) for row in rows])


def _metric_coverage(rows: list[dict], fields: tuple[str, ...]) -> dict[str, dict[str, float | int]]:
    total = len(rows)
    result: dict[str, dict[str, float | int]] = {}
    for field in fields:
        observed = sum(row.get(field) is not None for row in rows)
        result[field] = {
            "available": observed,
            "sample_size": total,
            "coverage": round(observed / total, 4) if total else 0,
        }
    return result


def _engagement(row: dict) -> tuple[float | None, list[str]]:
    reach = row.get("views")
    present = [field for field in INTERACTION_METRICS if row.get(field) is not None]
    if reach is None or reach <= 0 or not present:
        return None, present
    return social_stats.engagement_rate(sum(row[field] for field in present), reach), present


def _metric_summary(rows: list[dict], platform: Platform) -> dict:
    metrics = DOUYIN_METRICS if platform == Platform.DOUYIN else XHS_METRICS
    summary = {
        field: {
            "median": _number_median(rows, field),
            "available": sum(row.get(field) is not None for row in rows),
            "sample_size": len(rows),
        }
        for field in metrics
    }
    rates = []
    partial = 0
    for row in rows:
        rate, components = _engagement(row)
        if rate is not None:
            rates.append(rate)
            partial += len(components) < len(INTERACTION_METRICS)
    summary["engagement_rate"] = {
        "median": social_stats.median(rates),
        "available": len(rates),
        "sample_size": len(rows),
        "partial_interaction_rows": partial,
        "formula": "sum(available likes, comments, favorites, shares) / views; missing components are omitted, never imputed as zero",
        "rate_unit": "ratio (multiply by 100 for percent)",
    }
    summary["metric_coverage"] = _metric_coverage(rows, metrics)
    return summary


def _subject_groups(row: dict) -> list[str]:
    text = " ".join([*(row.get("subjects") or []), *(row.get("tags") or []), row.get("content_type") or ""])
    has_maine = "缅因" in text or "maine" in text.casefold()
    has_ragdoll = "布偶" in text or "ragdoll" in text.casefold()
    explicit_pair = "双猫" in text or "两只猫" in text or "两猫" in text
    groups: list[str] = []
    if has_maine and has_ragdoll or explicit_pair:
        groups.extend(["双猫", "缅因+布偶"] if has_maine and has_ragdoll else ["双猫"])
    elif has_maine:
        groups.extend(["单猫", "缅因"])
    elif has_ragdoll:
        groups.extend(["单猫", "布偶"])
    elif row.get("subjects"):
        groups.extend(["单主体", "已标注主体"])
    else:
        groups.append("未标注主体")
    return list(dict.fromkeys(groups))


def _duration_group(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 15:
        return "≤15秒"
    if value <= 30:
        return "16–30秒"
    if value <= 60:
        return "31–60秒"
    return ">60秒"


def _publish_period(value: str | None) -> str | None:
    if not value:
        return None
    try:
        hour = datetime.fromisoformat(value.replace("Z", "+00:00")).hour
    except ValueError:
        return None
    if hour < 6:
        return "00–06"
    if hour < 12:
        return "06–12"
    if hour < 18:
        return "12–18"
    return "18–24"


def _segment_values(rows: list[dict], platform: Platform) -> dict[str, dict[str, list[dict]]]:
    dimensions: dict[str, dict[str, list[dict]]] = {
        "content_source": defaultdict(list),
        "content_type": defaultdict(list),
        "hook": defaultdict(list),
    }
    if platform == Platform.DOUYIN:
        dimensions.update({"subjects": defaultdict(list), "duration": defaultdict(list), "publish_period": defaultdict(list)})
    for row in rows:
        source = row.get("content_source") or "UNKNOWN"
        dimensions["content_source"][source].append(row)
        content_type = (row.get("content_type") or "未分类").strip()
        dimensions["content_type"][content_type].append(row)
        dimensions["hook"]["有 Hook" if (row.get("hook_type") or "").strip() else "无 Hook"].append(row)
        if platform == Platform.DOUYIN:
            for subject in _subject_groups(row):
                dimensions["subjects"][subject].append(row)
            duration = _duration_group(row.get("duration"))
            if duration:
                dimensions["duration"][duration].append(row)
            period = _publish_period(row.get("publish_time"))
            if period:
                dimensions["publish_period"][period].append(row)
    return dimensions


def _distribution(rows: list[dict], platform: Platform) -> dict:
    result: dict[str, object] = {
        "content_source": dict(Counter(row.get("content_source") or "UNKNOWN" for row in rows)),
        "content_type": dict(Counter((row.get("content_type") or "未分类").strip() for row in rows)),
    }
    if platform == Platform.DOUYIN:
        subject_counts: Counter = Counter()
        for row in rows:
            subject_counts.update(_subject_groups(row))
        result.update({
            "subjects": dict(subject_counts),
            "hook": dict(Counter("有 Hook" if (row.get("hook_type") or "").strip() else "无 Hook" for row in rows)),
            "duration": dict(Counter(_duration_group(row.get("duration")) for row in rows if row.get("duration") is not None)),
            "publish_period": dict(Counter(_publish_period(row.get("publish_time")) for row in rows if _publish_period(row.get("publish_time")))),
        })
    return result


def _finding_confidence(a: list[dict], b: list[dict], overall: str) -> str:
    return _group_confidence(min(len(a), len(b)), overall)


def _pattern_findings(rows: list[dict], platform: Platform, overall_confidence: str) -> tuple[list[dict], list[str]]:
    dimensions = _segment_values(rows, platform)
    fields = DOUYIN_METRICS if platform == Platform.DOUYIN else XHS_METRICS
    findings: list[dict] = []
    insufficient: list[str] = []
    for dimension, groups in dimensions.items():
        eligible = [(name, values) for name, values in groups.items() if len(values) >= 2]
        small = [name for name, values in groups.items() if 0 < len(values) < 2]
        if small:
            insufficient.append(f"{dimension}: {', '.join(small)} 仅有 1 条样本，无法比较")
        if len(eligible) < 2:
            if len(groups) > 1:
                insufficient.append(f"{dimension}: 每组至少需要 2 条可比样本")
            continue
        for field in fields:
            ranked = [(name, values, _number_median(values, field)) for name, values in eligible]
            ranked = [item for item in ranked if item[2] is not None]
            if len(ranked) < 2:
                continue
            ranked.sort(key=lambda item: (item[2], item[0]))
            low = ranked[0]
            high = ranked[-1]
            if low[0] == high[0] or low[2] == high[2]:
                continue
            relative = (high[2] - low[2]) / max(abs(low[2]), 1) * 100
            findings.append({
                "dimension": dimension,
                "pattern": f"{high[0]} vs {low[0]}",
                "sample_a": len(high[1]),
                "sample_b": len(low[1]),
                "metric": f"{field}_median",
                "value_a": high[2],
                "value_b": low[2],
                "difference_percent": round(relative, 2),
                "direction": "higher" if high[2] > low[2] else "lower",
                "confidence": _finding_confidence(high[1], low[1], overall_confidence),
                "evidence_post_ids_a": [row["id"] for row in high[1]],
                "evidence_post_ids_b": [row["id"] for row in low[1]],
            })
    findings.sort(key=lambda item: (CONFIDENCE_ORDER[item["confidence"]], item["difference_percent"]), reverse=True)
    return findings[:50], list(dict.fromkeys(insufficient))


def _ranking_metric(rows: list[dict], platform: Platform) -> str:
    if platform == Platform.XIAOHONGSHU and any(row.get("favorites") is not None for row in rows):
        return "favorites"
    return "views"


def _ranked_posts(rows: list[dict], order: str, platform: Platform) -> list[dict]:
    metric = _ranking_metric(rows, platform)
    available = [row for row in rows if row.get(metric) is not None]
    available.sort(key=lambda row: (
        row[metric], row.get("views") if row.get("views") is not None else -1,
        row.get("publish_time") or "", row["id"],
    ))
    if order == "descending":
        available.reverse()
    return [{
        "id": row["id"], "title": row["title"], "publish_time": row.get("publish_time"),
        "content_type": row.get("content_type"), "content_source": row.get("content_source"),
        "subjects": row.get("subjects", []), "views": row.get("views"), "likes": row.get("likes"),
        "comments": row.get("comments"), "favorites": row.get("favorites"),
        "shares": row.get("shares"), "followers_gain": row.get("followers_gain"),
        "profile_visits": row.get("profile_visits"), "inquiries": row.get("inquiries"),
        "rank_basis": f"{metric}_{'desc' if order == 'descending' else 'asc'}",
    } for row in available[:5]]


def _rule_findings(rows: list[dict], platform: Platform, completeness: dict, metrics: dict, confidence: str,
                   pattern_findings: list[dict], insufficient: list[str]) -> dict[str, list[str]]:
    strengths: list[str] = []
    problems: list[str] = []
    opportunities: list[str] = []
    if completeness["score"] < 50:
        problems.append(f"历史数据完整度为 {completeness['score']}%，可用证据覆盖不足。")
    if len(rows) < 5:
        problems.append(f"当前仅有 {len(rows)} 条历史作品，整体判断置信度为 {confidence}。")
    reach = metrics["views"]["available"]
    if reach == 0:
        problems.append("没有作品提供播放/曝光数据，无法进行高低表现排序或互动率计算。")
    top = _ranked_posts(rows, "descending", platform)
    if top and confidence != "LOW":
        metric = _ranking_metric(rows, platform)
        label = "收藏" if metric == "favorites" else "播放/曝光"
        strengths.append(f"按{label}排序的最高作品为《{top[0]['title']}》（{top[0][metric]}），排序依据为 {metric}。")
    if pattern_findings:
        supported = [item for item in pattern_findings if item["confidence"] != "LOW"]
        for item in supported[:3]:
            strengths.append(
                f"{item['pattern']} 在 {item['metric']} 上呈现可观察差异；样本分别为 "
                f"{item['sample_a']} 与 {item['sample_b']}，置信度 {item['confidence']}。"
            )
            opportunities.append(
                f"可在后续内容中复测 {item['pattern']} 的差异；本诊断只记录历史表现，不据此确认运营策略。"
            )
    if not opportunities and pattern_findings:
        opportunities.append("当前分组差异样本有限；后续积累更多作品后可再次检验已有分组。")
    if insufficient:
        problems.append("部分内容分组或指标样本不足，不能支持稳定比较。")
    if not strengths:
        strengths.append("当前数据尚未支持稳定的相对优势判断；保留原始统计供后续样本积累。")
    if not opportunities:
        opportunities.append("继续补齐发布时间、内容类型与平台指标，再检验分组表现差异。")
    return {"strengths": strengths, "problems": problems, "opportunities": opportunities}


class AccountIntelligenceEngine:
    """Build deterministic evidence for initial diagnosis and later account reviews."""

    def analyze(self, *, account: dict, posts: list[dict], completeness: dict) -> dict:
        platform = Platform(account["platform"])
        sample_size = len(posts)
        metrics = _metric_summary(posts, platform)
        metric_fields = DOUYIN_METRICS if platform == Platform.DOUYIN else XHS_METRICS
        metric_coverage = mean([metrics["metric_coverage"][field]["coverage"] for field in metric_fields]) if metric_fields else 0
        confidence = confidence_level(sample_size, completeness["score"], metric_coverage or 0)
        pattern_findings, insufficient = _pattern_findings(posts, platform, confidence)
        if sample_size < 5:
            insufficient.append(f"整体历史样本仅 {sample_size} 条；分组和整体判断都应视为低置信度。")
        if metric_coverage < 0.4:
            insufficient.append(f"关键指标平均覆盖率为 {metric_coverage:.0%}，表现比较依据有限。")
        if completeness["score"] < 50:
            insufficient.append(f"历史数据完整度仅 {completeness['score']}%，结论可信度有限。")
        insufficient = list(dict.fromkeys(insufficient))
        data_quality = {
            "sample_size": sample_size,
            "completeness": completeness,
            "metric_coverage": metrics["metric_coverage"],
            "overall_metric_coverage": round(metric_coverage or 0, 4),
            "confidence": confidence,
            "confidence_rules": {
                "HIGH": "sample_size >= 20, completeness >= 80, overall metric coverage >= 70%",
                "MEDIUM": "sample_size >= 8, completeness >= 50, overall metric coverage >= 40%",
                "otherwise": "LOW",
            },
        }
        report = {
            "status": "COMPLETED",
            "platform": platform.value,
            "account": {
                "id": account["id"], "name": account["name"], "platform": platform.value,
                "status": account["status"],
            },
            "account_context": {
                "profile_summary": (account.get("profile") or {}).get("summary", ""),
                "strategy_summary": (account.get("strategy") or {}).get("summary", ""),
                "strategy_state": (account.get("strategy") or {}).get("state"),
                "strategy_is_initial_hypothesis": (account.get("strategy") or {}).get("state") == "hypothesis",
                "used_as_conclusion_source": False,
            },
            "input_evidence": {
                "historical_post_ids": [row["id"] for row in posts],
                "historical_post_versions": [
                    {"id": row["id"], "updated_at": row["updated_at"]} for row in posts
                ],
                "sample_size": sample_size,
                "algorithm_version": ALGORITHM_VERSION,
            },
            "overview": f"读取 {sample_size} 条历史作品；当前为 {confidence} 置信度的描述性诊断，不自动生成 Baseline 或运营策略。",
            "data_quality": data_quality,
            "content_distribution": _distribution(posts, platform),
            "metric_summary": metrics,
            "top_posts": _ranked_posts(posts, "descending", platform),
            "low_posts": _ranked_posts(posts, "ascending", platform),
            "pattern_findings": pattern_findings,
            "strengths": [], "problems": [], "opportunities": [],
            "insufficient_data": insufficient,
            "confidence": confidence,
            "analysis_scope": "historical_posts_only",
            "ranking_rule": f"Top/Low 排序依据为 {_ranking_metric(posts, platform)}；缺少该指标的作品不参与排序。",
            "engagement_rate_formula": "per post: sum(available likes, comments, favorites, shares) / views; missing metrics are omitted, not imputed; views must be > 0",
            "generated_at": None,
        }
        narrative = _rule_findings(posts, platform, completeness, metrics, confidence, pattern_findings, insufficient)
        report.update(narrative)
        if platform == Platform.XIAOHONGSHU:
            favorites = metrics["favorites"]["median"]
            views = metrics["views"]["median"]
            favorite_rates = [
                social_stats.engagement_rate(row["favorites"], row["views"])
                for row in posts if row.get("favorites") is not None and row.get("views") is not None and row["views"] > 0
            ]
            if favorite_rates and len(favorite_rates) >= 3:
                report["save_value_signal"] = {
                    "observed": True, "favorites_median": favorites, "views_median": views,
                    "favorites_to_views_median": social_stats.median(favorite_rates),
                    "sample_size": len(favorite_rates),
                    "formula": "favorites / views for rows with both metrics and views > 0",
                    "note": "收藏相对曝光可作为实用价值候选信号；仅描述观察，不据此确定策略。",
                }
            else:
                report["save_value_signal"] = {
                    "observed": False, "sample_size": len(favorite_rates),
                    "note": "收藏与曝光同时存在的样本少于 3 条，暂不能识别实用价值信号。",
                }
            report["ip_business_signals"] = {
                "profile_visits_median": metrics["profile_visits"]["median"],
                "inquiries_median": metrics["inquiries"]["median"],
                "interpretation": "仅作为后续分析输入，本阶段不调整 Strategy。",
            }
        return report
