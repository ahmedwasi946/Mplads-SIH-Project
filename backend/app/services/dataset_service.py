import csv
import io
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


@dataclass(frozen=True)
class ParsedDataset:
    columns: list[str]
    rows: list[dict[str, str]]

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def total_columns(self) -> int:
        return len(self.columns)


def get_upload_directory() -> Path:
    upload_directory = Path(settings.uploads_dir)
    upload_directory.mkdir(parents=True, exist_ok=True)
    return upload_directory


def create_stored_filename() -> str:
    return f"{uuid4().hex}.csv"


def save_uploaded_file(contents: bytes, stored_filename: str) -> Path:
    destination = get_upload_directory() / stored_filename
    destination.write_bytes(contents)
    return destination


def remove_uploaded_file(stored_filename: str) -> None:
    destination = get_upload_directory() / stored_filename
    destination.unlink(missing_ok=True)


def parse_csv_contents(contents: bytes) -> ParsedDataset:
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must be valid UTF-8 text.") from exc

    if not text.strip():
        raise ValueError("CSV file is empty.")

    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise ValueError("CSV file could not be parsed.") from exc

    if not rows:
        raise ValueError("CSV file is empty.")

    columns = [column.strip() for column in rows[0]]
    if not columns or any(not column for column in columns):
        raise ValueError("CSV file must contain non-empty column names.")
    if len(set(columns)) != len(columns):
        raise ValueError("CSV file must not contain duplicate column names.")

    parsed_rows: list[dict[str, str]] = []
    for row_number, values in enumerate(rows[1:], start=2):
        if len(values) != len(columns):
            raise ValueError(
                f"CSV row {row_number} has {len(values)} values; "
                f"expected {len(columns)}."
            )
        parsed_rows.append(dict(zip(columns, values)))

    return ParsedDataset(columns=columns, rows=parsed_rows)


def parse_csv_file(path: Path) -> ParsedDataset:
    try:
        return parse_csv_contents(path.read_bytes())
    except OSError as exc:
        raise ValueError("Uploaded CSV file could not be read.") from exc