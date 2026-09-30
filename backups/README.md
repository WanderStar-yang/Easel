# Social Operator SQLite Snapshot

`social_operator_2026-09-30.sqlite3` is a consistent SQLite online backup of the live Social Operator database at `outputs/_social_operator.sqlite3`, created on 2026-09-30.

The snapshot passed `PRAGMA integrity_check`. It contains 82 active historical posts, 202 archived legacy rows, one Account Baseline, and eight diagnosis records. Classification metadata and suggestion tables are present but empty in this snapshot; real AI classification and Baseline V2 have not yet been completed.

The live database remains ignored under `outputs/`; this dated snapshot is committed separately so routine application writes do not modify the backup. The application's local `.env` and API keys are not stored in this database or included in this snapshot.
