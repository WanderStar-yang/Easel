# Social Operator SQLite Snapshot

`social_operator_2026-09-30.sqlite3` is the pre-classification Social Operator database snapshot created on 2026-09-30. It preserves the state before real Phase 4.5 acceptance.

`social_operator_2026-09-30_phase4-5.sqlite3` is the current post-acceptance snapshot of `outputs/_social_operator.sqlite3`, created with SQLite's online backup API. It passed `PRAGMA integrity_check` and contains 82 active canonical posts, 202 archived legacy rows, 82 classification suggestion records, confirmed classification metadata, and Baseline V1 (STALE) plus V2 (ACTIVE). V2 has sample size 82.

The live database remains ignored under `outputs/`; dated snapshots are committed separately so routine application writes do not modify them. The application's local `.env` and API keys are not stored in the database or included in these snapshots.
