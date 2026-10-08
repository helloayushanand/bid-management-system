"""Configuration for bounded batch processing."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from config.settings import load_environment


def _boolean(name: str, default: bool) -> bool:
    value=os.getenv(name,str(default)).strip().lower()
    if value in {"1","true","yes","on"}: return True
    if value in {"0","false","no","off"}: return False
    raise ValueError(f"{name} must be true or false.")

@dataclass(frozen=True)
class BatchSettings:
    maximum_documents: int=10
    maximum_file_size_mb: int=200
    working_root: Path=Path("temp")/"batches"
    preserve_completed_batches: bool=True
    native_workers: int=2
    ocr_workers: int=1
    multiprocessing_enabled: bool=True

    @classmethod
    def from_environment(cls) -> "BatchSettings":
        load_environment()
        settings=cls(
            maximum_documents=int(os.getenv("BATCH_MAX_DOCUMENTS","10")),
            maximum_file_size_mb=int(os.getenv("BATCH_MAX_FILE_SIZE_MB","200")),
            working_root=Path(os.getenv("BATCH_WORKING_ROOT","temp/batches")),
            preserve_completed_batches=_boolean("BATCH_PRESERVE_COMPLETED",True),
            native_workers=int(os.getenv("BATCH_NATIVE_WORKERS","2")),
            ocr_workers=int(os.getenv("BATCH_OCR_WORKERS","1")),
            multiprocessing_enabled=_boolean("BATCH_MULTIPROCESSING_ENABLED",True),
        )
        if not 1 <= settings.maximum_documents <= 10: raise ValueError("BATCH_MAX_DOCUMENTS must be between 1 and 10.")
        if settings.maximum_file_size_mb < 1: raise ValueError("BATCH_MAX_FILE_SIZE_MB must be positive.")
        if not 1 <= settings.native_workers <= 4: raise ValueError("BATCH_NATIVE_WORKERS must be between 1 and 4.")
        if not 1 <= settings.ocr_workers <= 2: raise ValueError("BATCH_OCR_WORKERS must be between 1 and 2.")
        return settings
