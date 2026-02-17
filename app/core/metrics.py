from dataclasses import dataclass
from threading import Lock


@dataclass
class _MetricsState:
    total_uploads: int = 0
    duplicates: int = 0
    gemini_calls: int = 0
    sheets_append_success: int = 0
    sheets_append_failure: int = 0
    total_processing_seconds: float = 0.0


class MetricsTracker:
    def __init__(self) -> None:
        self._state = _MetricsState()
        self._lock = Lock()

    def record_upload(self, processing_seconds: float, duplicate: bool) -> None:
        with self._lock:
            self._state.total_uploads += 1
            self._state.total_processing_seconds += max(processing_seconds, 0.0)
            if duplicate:
                self._state.duplicates += 1

    def record_gemini_call(self) -> None:
        with self._lock:
            self._state.gemini_calls += 1

    def record_sheets_append(self, success: bool) -> None:
        with self._lock:
            if success:
                self._state.sheets_append_success += 1
            else:
                self._state.sheets_append_failure += 1


    def reset(self) -> None:
        with self._lock:
            self._state = _MetricsState()

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            avg_processing = (
                self._state.total_processing_seconds / self._state.total_uploads
                if self._state.total_uploads
                else 0.0
            )
            return {
                "total_uploads": self._state.total_uploads,
                "duplicates": self._state.duplicates,
                "gemini_calls": self._state.gemini_calls,
                "sheets_append_success": self._state.sheets_append_success,
                "sheets_append_failure": self._state.sheets_append_failure,
                "avg_processing_seconds": round(avg_processing, 3),
            }


metrics_tracker = MetricsTracker()
