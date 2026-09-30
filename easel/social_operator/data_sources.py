"""Adapters for manual and generic file entry into HistoricalPost."""


class FileImportAdapter:
    source = "FILE_IMPORT"

    def adapt(self, records: list[dict]) -> list[dict]:
        return [dict(record) for record in records]


class ManualInputAdapter:
    source = "MANUAL"

    def adapt(self, records: list[dict]) -> list[dict]:
        return [dict(record) for record in records]
