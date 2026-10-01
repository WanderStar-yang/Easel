# Social Operator SQLite Snapshots

SQLite snapshots contain real account data. Keep database files local and do not commit them. Files under `backups/` with SQLite extensions and the live database under `outputs/` are excluded by `.gitignore`.

Older snapshots were committed before this local-only policy was added. This change removes them from the current Git tree but does not rewrite remote Git history.
