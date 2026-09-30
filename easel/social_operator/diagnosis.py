"""Initial diagnosis orchestration and optional explanation via Easel's gateway."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from .historical import HistoricalPostService
from .canonical import canonical_unique_posts, suspected_duplicate_count
from .intelligence import ALGORITHM_VERSION, AccountIntelligenceEngine
from .models import AccountDiagnosis, AccountStatus
from .repository import OperatorAccountRepository
from .service import OperatorAccountService


class InsufficientHistoryError(ValueError):
    code = "INSUFFICIENT_DATA"


class DiagnosisStateError(ValueError):
    pass


class DiagnosisExplainer(Protocol):
    def explain(self, report: dict) -> dict[str, str | None]: ...


class UnavailableExplainer:
    def explain(self, report: dict) -> dict[str, str | None]:
        del report
        return {"status": "unavailable", "provider": None, "summary": None, "reason": "not_configured"}


class OpenClawDiagnosisExplainer:
    """Ask the already configured Easel/OpenClaw model to explain computed evidence only."""

    def __init__(self, timeout_seconds: float = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def explain(self, report: dict) -> dict[str, str | None]:
        try:
            import httpx
            from easel.gateway_endpoint import chat_completions_url, healthz_url

            timeout = httpx.Timeout(self.timeout_seconds, connect=0.4)
            with httpx.Client(timeout=timeout) as client:
                health = client.get(healthz_url())
                if health.status_code >= 400:
                    return self._unavailable("gateway_unavailable")
                evidence = {
                    key: report.get(key) for key in (
                        "platform", "overview", "data_quality", "content_distribution",
                        "metric_summary", "pattern_findings", "top_posts", "low_posts",
                        "insufficient_data", "account_context", "input_evidence", "ranking_rule",
                    )
                }
                response = client.post(
                    chat_completions_url(),
                    headers={"x-openclaw-session-key": f"agent:main:diagnosis:{uuid4().hex}"},
                    json={
                        "model": "openclaw/default",
                        "stream": False,
                        "temperature": 0.2,
                        "max_tokens": 900,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "你是账号历史数据诊断报告的解释器。只能解释输入中的结构化证据，不能重新计算、"
                                    "改写或补造任何数值；不能把相关性说成因果，不能用 Profile/Strategy 假设替代历史数据。"
                                    "不要提出已确认定位、Content Pillars、Baseline 或正式运营策略。指出样本限制，"
                                    "用简体中文写 3-6 句，必要时明确说数据不足。"
                                ),
                            },
                            {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
                        ],
                    },
                )
                if response.status_code != 200:
                    return self._unavailable(f"http_{response.status_code}")
                payload = response.json()
                summary = payload["choices"][0]["message"]["content"]
                if isinstance(summary, list):
                    summary = "".join(
                        part.get("text", "") for part in summary if isinstance(part, dict)
                    )
                summary = str(summary or "").strip()[:4000]
                if not summary:
                    return self._unavailable("empty_response")
                return {"status": "available", "provider": "easel_openclaw_gateway", "summary": summary, "reason": None}
        except Exception as exc:  # LLM failure must never block deterministic diagnosis.
            return self._unavailable(type(exc).__name__)

    @staticmethod
    def _unavailable(reason: str) -> dict[str, str | None]:
        return {"status": "unavailable", "provider": "easel_openclaw_gateway", "summary": None,
                "reason": reason}


class AccountDiagnosisService:
    def __init__(self, repository: OperatorAccountRepository | None = None, *,
                 engine: AccountIntelligenceEngine | None = None,
                 explainer: DiagnosisExplainer | None = None) -> None:
        self.repository = repository or OperatorAccountRepository()
        self.accounts = OperatorAccountService(self.repository)
        self.posts = HistoricalPostService(self.repository)
        self.engine = engine or AccountIntelligenceEngine()
        self.explainer = explainer or UnavailableExplainer()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def diagnose(self, account_id: str) -> AccountDiagnosis:
        account = self.accounts.get_account(account_id)
        raw_rows = self.repository.list_posts(account_id, limit=100000)
        rows = canonical_unique_posts(raw_rows)
        if not rows:
            raise InsufficientHistoryError("暂无历史内容，请先导入历史数据。")
        if account.status not in {AccountStatus.NEW, AccountStatus.IMPORTING, AccountStatus.DIAGNOSING}:
            raise DiagnosisStateError(f"当前账号状态 {account.status.value} 不支持首次诊断。")

        if account.status == AccountStatus.NEW:
            self.accounts.update_account(account_id, {"status": AccountStatus.IMPORTING.value})
            self.accounts.update_account(account_id, {"status": AccountStatus.DIAGNOSING.value})
        elif account.status == AccountStatus.IMPORTING:
            self.accounts.update_account(account_id, {"status": AccountStatus.DIAGNOSING.value})

        account_row = self.repository.get_account(account_id)
        completeness = self.posts.completeness(account_id)
        report = self.engine.analyze(
            account=account_row, posts=rows, completeness=completeness,
            raw_record_count=len(raw_rows),
            excluded_stale_count=sum(row.get("source_presence") == "MISSING" for row in raw_rows),
            suspected_duplicates=suspected_duplicate_count(raw_rows),
            archived_legacy_count=self.repository.count_archived_posts(account_id),
        )
        generated_at = self._now()
        report["generated_at"] = generated_at
        report["ai_explanation"] = self.explainer.explain(report)
        diagnosis_id = str(uuid4())
        stored = self.repository.save_diagnosis(
            diagnosis_id, account_id, ALGORITHM_VERSION,
            json.dumps(report, ensure_ascii=False, allow_nan=False), generated_at,
        )
        return self._to_model(stored)

    def get_latest(self, account_id: str) -> AccountDiagnosis:
        self.accounts.get_account(account_id)
        row = self.repository.get_latest_diagnosis(account_id)
        if row is None:
            raise LookupError(account_id)
        return self._to_model(row)

    def list_history(self, account_id: str, limit: int = 20) -> list[AccountDiagnosis]:
        self.accounts.get_account(account_id)
        return [self._to_model(row) for row in self.repository.list_diagnoses(account_id, limit=limit)]

    @staticmethod
    def _to_model(row: dict) -> AccountDiagnosis:
        report = dict(row["report"])
        if row.get("status") == "STALE":
            report["status"] = "STALE"
            report["stale_at"] = row.get("stale_at")
            report["stale_reason"] = row.get("stale_reason")
        return AccountDiagnosis(
            id=row["id"], account_id=row["account_id"], generated_at=row["generated_at"],
            algorithm_version=row["algorithm_version"], report=report,
        )
