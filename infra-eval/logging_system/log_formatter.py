"""
Log formatter and CSV export module.

Provides a JSON formatter for the standard :mod:`logging` module plus a
thread-safe CSV exporter that can convert structured JSON log files into
comma-separated values for downstream analysis.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TextIO

#: Default fields included when exporting to CSV.
DEFAULT_CSV_FIELDS: List[str] = [
    "timestamp",
    "level",
    "event_type",
    "user_prompt",
    "sanitized_prompt",
    "ai_response",
    "tool_used",
    "risk_score",
    "decision",
    "execution_time_ms",
    "cpu_usage_percent",
    "memory_usage_mb",
    "container_id",
    "status",
    "error_message",
]


class JSONFormatter(logging.Formatter):
    """
    A logging formatter that emits records as JSON lines.

    Each log record is serialised to a single-line JSON object. Any
    attributes present on the record are captured so callers can attach
    arbitrary structured fields (e.g. ``risk_score``, ``container_id``).
    """

    def __init__(
        self,
        include_timestamp: bool = True,
        include_stack_info: bool = False,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
    ) -> None:
        """
        Initialise the JSON formatter.

        Args:
            include_timestamp: Include an ISO-8601 UTC timestamp in output.
            include_stack_info: Attach ``stack_info`` to the record output.
            fmt: Optional format string (kept for ``logging.Formatter`` compat).
            datefmt: Optional date format (kept for compatibility).
        """
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.include_timestamp = include_timestamp
        self.include_stack_info = include_stack_info

    def _default_fields(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract the default structured fields from a log record."""
        fields: Dict[str, Any] = {
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if self.include_timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()
            fields["timestamp"] = timestamp
        if self.include_stack_info and record.stack_info:
            fields["stack_info"] = record.stack_info
        if record.exc_info:
            fields["exception"] = self._format_exception(record)
        return fields

    @staticmethod
    def _format_exception(record: logging.LogRecord) -> str:
        """
        Format the exception attached to a log record.

        Handles records where ``exc_info`` is ``True`` (a boolean flag) by
        resolving the currently active exception via :func:`sys.exc_info`.

        Args:
            record: The log record to inspect.

        Returns:
            A formatted exception traceback string.
        """
        exc_info: Any = record.exc_info
        if exc_info is True:
            exc_info = sys.exc_info()
        if exc_info and exc_info[0] is not None:
            return "".join(traceback.format_exception(*exc_info))
        return str(exc_info)

    def _extra_fields(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract custom attributes attached to the log record."""
        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
        }
        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in reserved and not key.startswith("_")
        }

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        """
        Format a log record as a JSON line.

        Args:
            record: The log record to format.

        Returns:
            A JSON-encoded string.
        """
        payload: Dict[str, Any] = {}
        payload.update(self._default_fields(record))
        payload.update(self._extra_fields(record))
        return json.dumps(payload, default=str)


class CSVExporter:
    """
    Thread-safe exporter that writes structured log data to CSV files.

    The exporter maps :class:`LogEntry` dictionaries (or flat JSON objects)
    onto a fixed set of columns. Missing values are emitted as empty cells.
    """

    def __init__(
        self,
        fields: Optional[Iterable[str]] = None,
        delimiter: str = ",",
    ) -> None:
        """
        Initialise the CSV exporter.

        Args:
            fields: Ordered column names. Defaults to
                :data:`DEFAULT_CSV_FIELDS`.
            delimiter: Field delimiter (default comma).
        """
        self.fields: List[str] = list(fields) if fields else list(DEFAULT_CSV_FIELDS)
        self.delimiter = delimiter
        self._lock = threading.RLock()

    @property
    def column_names(self) -> List[str]:
        """Return the ordered column names for the CSV output."""
        return list(self.fields)

    def _writer_for(self, csv_file: TextIO) -> csv.DictWriter:
        """Create a configured DictWriter bound to an open file handle."""
        return csv.DictWriter(
            csv_file,
            fieldnames=self.fields,
            delimiter=self.delimiter,
            extrasaction="ignore",
            restval="",
            lineterminator="\n",
        )

    def write_header(self, csv_file: TextIO) -> None:
        """
        Write the CSV header row to an open file handle.

        Args:
            csv_file: An open, writable text stream.
        """
        with self._lock:
            self._writer_for(csv_file).writeheader()

    def export_rows(
        self,
        csv_file: TextIO,
        rows: Iterable[Dict[str, Any]],
        include_header: bool = False,
    ) -> int:
        """
        Write a sequence of row dictionaries to an open CSV file.

        Args:
            csv_file: An open, writable text stream.
            rows: Iterable of flat dictionaries keyed by column name.
            include_header: Write the header row before data when ``True``.

        Returns:
            Number of rows written.
        """
        writer = self._writer_for(csv_file)
        count = 0
        with self._lock:
            if include_header:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)
                count += 1
        return count

    def export_file(
        self,
        json_log_path: Path,
        csv_output_path: Path,
        include_header: bool = True,
    ) -> int:
        """
        Convert a JSON-lines log file into a CSV file.

        Args:
            json_log_path: Path to the source JSON-lines log file.
            csv_output_path: Destination path for the CSV file.
            include_header: Include a header row in the output.

        Returns:
            Number of rows written.

        Raises:
            FileNotFoundError: If the source file does not exist.
            json.JSONDecodeError: If a line is not valid JSON.
        """
        json_log_path = Path(json_log_path)
        csv_output_path = Path(csv_output_path)
        if not json_log_path.exists():
            raise FileNotFoundError(f"Log file not found: {json_log_path}")

        csv_output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with self._lock:
            with open(csv_output_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = self._writer_for(csv_file)
                if include_header:
                    writer.writeheader()
                with open(json_log_path, "r", encoding="utf-8") as json_file:
                    for line in json_file:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        writer.writerow(record)
                        count += 1
        return count

    def export_log_entries(
        self,
        csv_output_path: Path,
        entries: Iterable[Dict[str, Any]],
        include_header: bool = True,
    ) -> int:
        """
        Export a collection of log entry dictionaries to a CSV file.

        Args:
            csv_output_path: Destination path for the CSV file.
            entries: Iterable of :class:`LogEntry` dictionaries.
            include_header: Include a header row in the output.

        Returns:
            Number of rows written.
        """
        csv_output_path = Path(csv_output_path)
        csv_output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with self._lock:
            with open(csv_output_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = self._writer_for(csv_file)
                if include_header:
                    writer.writeheader()
                for entry in entries:
                    writer.writerow(entry)
                    count += 1
        return count

    def read_csv(self, csv_path: Path) -> List[Dict[str, str]]:
        """
        Read a CSV file back into a list of dictionaries.

        Args:
            csv_path: Path to the CSV file to read.

        Returns:
            List of row dictionaries keyed by column name.
        """
        csv_path = Path(csv_path)
        with self._lock:
            with open(csv_path, "r", newline="", encoding="utf-8") as csv_file:
                reader = csv.DictReader(csv_file, delimiter=self.delimiter)
                return [dict(row) for row in reader]


# Alias for convenience
def create_csv_exporter(
    fields: Optional[Iterable[str]] = None,
    delimiter: str = ",",
) -> CSVExporter:
    """
    Factory for creating a :class:`CSVExporter`.

    Args:
        fields: Optional ordered column names.
        delimiter: Field delimiter.

    Returns:
        A configured :class:`CSVExporter`.
    """
    return CSVExporter(fields=fields, delimiter=delimiter)
