"""Configuration for bounded batch processing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from config.settings import load_environment


@dataclass(frozen=True)
class BatchSettings:
    maximum_documents: int = 10
    maximum_file_size_mb: int = 200
    working_root: Path = Path("temp") / "batches"
    preserve_completed_batches: bool = True

    @classmethod
    def from_environment(cls) -> "BatchSettings":
        load_environment()

        maximum_documents = int(
            os.getenv("BATCH_MAX_DOCUMENTS", "10")
        )
        maximum_file_size_mb = int(
            os.getenv("BATCH_MAX_FILE_SIZE_MB", "200")
        )
        working_root = Path(
            os.getenv("BATCH_WORKING_ROOT", "temp/batches")
        )
        preserve = os.getenv(
            "BATCH_PRESERVE_COMPLETED", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}

        if maximum_documents < 1 or maximum_documents > 10:
            raise ValueError(
                "BATCH_MAX_DOCUMENTS must be between 1 and 10."
            )
        if maximum_file_size_mb < 1:
            raise ValueError(
                "BATCH_MAX_FILE_SIZE_MB must be positive."
            )

        return cls(
            maximum_documents=maximum_documents,
            maximum_file_size_mb=maximum_file_size_mb,
            working_root=working_root,
            preserve_completed_batches=preserve,
        )
