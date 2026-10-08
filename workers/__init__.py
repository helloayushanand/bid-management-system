"""Process-safe worker entry points."""
from workers.native_worker import run_native_inspection_job
from workers.ocr_worker import run_ocr_job

__all__ = ["run_native_inspection_job", "run_ocr_job"]
