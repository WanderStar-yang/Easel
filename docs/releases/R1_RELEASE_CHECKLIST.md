# R1 Release Checklist

**Release candidate:** R1 / V1.0.0-rc1
**Review date:** 2026-10-01
**Current decision:** R1-RC code checks and the two required real-account UI smoke flows pass. The requested candidate is R1 / V1.0.0-rc1; this does not announce a V1.0.0 release.

Status means code and flow readiness unless an item explicitly says “real-account”. Test fixtures live only in isolated test databases.

## Product flow

- [x] Two business accounts can be managed independently.
- [x] Historical data import, diagnosis, and canonical-post repair are implemented.
- [x] Account Baseline and Strategy Recommendation are versioned and account-scoped.
- [x] Strategy Confirmation activates the selected strategy and its content directions.
- [x] Today Operations provides three candidates, one primary, selection, and explanation.
- [x] Content Generation creates reviewable, editable, versioned drafts for Douyin and Xiaohongshu.
- [x] Content Calendar plans selected topics and records manual publication facts only.
- [x] Published Data supports platform work ID and 24H / 72H / 7D metrics; missing values remain unknown.
- [x] Weekly Review computes statistics from real publication records and blocks insufficient samples.
- [x] Strategy Memory requires explicit user acceptance and is included in later topic context.
- [x] Publication → metrics → Weekly Review → accepted Memory → next-topic cycle is covered by the isolated R1 core integration test. The real-account smoke intentionally stops at Calendar; no real publication was required for RC and no fake data was entered.

## Release candidate integration

- [x] Main landing page opens on “今日运营”; legacy Easel areas are secondary.
- [x] Weekly pillar progress is calculated only from actual published posts; today’s planned-item count is read from Calendar.
- [x] Selected drafts provide a direct action to arrange a publish time.
- [x] Unelapsed metric checkpoints show “等待数据”.
- [x] Xiaohongshu no-history mode says recommendations rely on account positioning and have no historical performance basis.
- [x] Insufficient weekly data displays “当前发布样本不足，暂无法形成有效周复盘。”
- [x] User-facing review labels avoid internal status values and raw metric-field identifiers.
- [x] Real Douyin account UI smoke: existing selected topic and V3 draft → Calendar plan. No publication or metrics were entered.
- [x] Real Xiaohongshu UI smoke: no-history recommendation → selected topic → real AI article draft V1 → Calendar plan.

## Security, persistence, and quality

- [x] `.env` and the real SQLite database are ignored by Git; model secrets are not written into source or docs.
- [x] A pre-RC real database backup was created and verified before the schema migration.
- [x] SQLite schema migration is additive from v16 to v17 and preserves the 82 canonical historical posts.
- [x] R1 core integration test uses isolated SQLite and mock AI across topic, draft, calendar, publication fixture, metrics, review, memory acceptance, and next-topic generation.
- [x] Full Python test suite after final integration changes.
- [x] Frontend production build after final integration changes.
- [x] Frontend lint after final integration changes.
- [x] `git diff --check` after final integration changes.

## Known release notes and decision

- No actual PublishedPost, performance metrics, Weekly Review, or Strategy Memory exists in the real account yet. This is expected for the requested RC smoke, which stops at Calendar; Weekly Review correctly remains unavailable until sufficient real samples are later recorded.
- The real UI smoke created two user-intended Calendar plans for 2026-10-02 20:00 Asia/Shanghai: Douyin selected-topic draft V3 and Xiaohongshu selected-topic draft V1. These are future plans only; no post was marked published and no metrics were entered.
- The configured Qwen-compatible provider completed a real Xiaohongshu draft request. One compatible-model omission (empty reader-interaction field) is now normalized to a neutral editable question; other missing required fields remain rejected. The draft still requires the account owner to fact-check and edit personal examples before use.
- Account switching in Calendar now clears the previous account's selected-topic ID, so a valid topic from the newly selected account enables scheduling.
- The app-wide conversation status uses user-facing wording instead of exposing “Gateway”, and is distinguished from model-provider availability.
- Final verification: Python 468 passed / 6 skipped; frontend build passed (535.01 kB main bundle warning); lint passed with two existing warnings; `git diff --check` passed.
- The main Vite bundle exceeds 500 kB; keep as a V1.1 performance backlog item if real page loading is acceptable.
- Two existing lint warnings remain in `linkifyOutputs.ts` and `AccountsPage.tsx`; track for V1.1 unless they change or block this release.
- Release candidate label may be prepared as `V1.0.0-rc1`. This task does not create a Git tag or announce the formal `V1.0.0` release.
