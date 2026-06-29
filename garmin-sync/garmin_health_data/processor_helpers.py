"""
Helper classes and functions for the Garmin data processor.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from garmin_health_data.db import check_sqlite_version

# Lowest SQLITE_MAX_VARIABLE_NUMBER across supported builds.
# Pre-3.32.0 defaulted to 999; 3.32.0+ raised it to 32 766.
# Using the floor guarantees safety on all platforms.
_SQLITE_MAX_PARAMS = 999


@dataclass
class FileSet:
    """
    Represents a set of files to process together.
    """

    file_paths: List[Path]
    files: Dict[Any, List[Path]]  # Maps data type enum to file paths


class Processor:
    """
    Base processor class for handling file sets.
    """

    def __init__(self, file_set: FileSet, session: Session):
        """
        Initialize processor.

        :param file_set: FileSet to process.
        :param session: SQLAlchemy session.
        """
        self.file_set = file_set
        self.session = session

    def process_file_set(self, file_set: FileSet, session: Session):
        """
        Process a file set.

        Override in subclasses.
        :param file_set: FileSet to process.
        :param session: SQLAlchemy session.
        """
        raise NotImplementedError("Subclasses must implement process_file_set")


def _use_postgresql() -> bool:
    """
    Return True if the current environment is configured for PostgreSQL.

    :return: True when ``DATABASE_URL`` starts with a PostgreSQL scheme.
    """
    url = os.environ.get("DATABASE_URL", "")
    return url.startswith("postgresql://") or url.startswith("postgres://")


def upsert_model_instances(
    session: Session,
    model_instances: List[Any],
    conflict_columns: List[str],
    on_conflict_update: bool = True,
    update_columns: Optional[List[str]] = None,
    returning_columns: Optional[List[str]] = None,
) -> List[Any]:
    """
    Bulk upsert SQLAlchemy ORM model instances into database tables.

    Supports both SQLite and PostgreSQL. When ``DATABASE_URL`` points to PostgreSQL, the
    helper uses PostgreSQL's ``INSERT ... ON CONFLICT`` syntax. For SQLite, the SQLite
    dialect's specialised insert is used.

    Large batches are automatically split into chunks to stay within database parameter
    limits.

    When ``returning_columns`` is omitted (default), the input list is returned
    unchanged. When provided, the listed columns are read back from the database via
    ``RETURNING``.

    :param session: SQLAlchemy session.
    :param model_instances: List of model instances to upsert.
    :param conflict_columns: Column **names** (database column names, matching
        ``Column.name``) forming the unique conflict target.
    :param on_conflict_update: If True, update on conflict; if False, ignore.
    :param update_columns: Column **keys** (Python attribute names, matching
        ``Column.key``) to update on conflict. Defaults to all columns except the
        conflict columns, primary-key columns, ``create_ts``, and ``update_ts``.
    :param returning_columns: Column **keys** to populate on the returned instances. If
        None, the input list is returned unchanged.
    :return: List of model instances.
    """
    if not model_instances:
        return []

    model_class = type(model_instances[0])
    model_columns = model_class.__table__.columns.keys()
    column_names = {col.name for col in model_class.__table__.columns}
    name_to_key = {col.name: col.key for col in model_class.__table__.columns}

    def _duplicates(seq: List[str]) -> List[str]:
        seen: set = set()
        dups: List[str] = []
        for item in seq:
            if item in seen and item not in dups:
                dups.append(item)
            seen.add(item)
        return dups

    if not conflict_columns:
        raise ValueError(
            "`conflict_columns` must be a non-empty list. An empty list "
            "produces invalid `ON CONFLICT` SQL in both DO UPDATE and DO "
            "NOTHING modes."
        )
    unknown_conflict = [c for c in conflict_columns if c not in column_names]
    if unknown_conflict:
        raise ValueError(
            f"`conflict_columns` references column name(s) not present on "
            f"{model_class.__name__}: {unknown_conflict}. Valid column "
            f"names: {sorted(column_names)}"
        )
    dup_conflict = _duplicates(conflict_columns)
    if dup_conflict:
        raise ValueError(
            f"`conflict_columns` contains duplicate entries: {dup_conflict}."
        )
    if update_columns is not None:
        unknown_update = [c for c in update_columns if c not in model_columns]
        if unknown_update:
            raise ValueError(
                f"`update_columns` references column key(s) not present on "
                f"{model_class.__name__}: {unknown_update}. Valid column "
                f"keys: {sorted(model_columns)}"
            )
        dup_update = _duplicates(update_columns)
        if dup_update:
            raise ValueError(
                f"`update_columns` contains duplicate entries: {dup_update}."
            )
    if returning_columns is not None:
        if not returning_columns:
            raise ValueError(
                "`returning_columns` must be a non-empty list when provided. "
                "Pass None to opt out of the RETURNING path."
            )
        unknown_returning = [c for c in returning_columns if c not in model_columns]
        if unknown_returning:
            raise ValueError(
                f"`returning_columns` references column key(s) not present "
                f"on {model_class.__name__}: {unknown_returning}. Valid "
                f"column keys: {sorted(model_columns)}"
            )
        dup_returning = _duplicates(returning_columns)
        if dup_returning:
            raise ValueError(
                f"`returning_columns` contains duplicate entries: "
                f"{dup_returning}. Duplicate column labels in RETURNING "
                f"would silently collide in the result dict."
            )
        if not _use_postgresql():
            check_sqlite_version()

    # Convert all instances to dictionaries (bulk preparation).
    values = []
    for instance in model_instances:
        instance_dict = {}
        for key, value in instance.__dict__.items():
            if key in model_columns:
                instance_dict[key] = value
        values.append(instance_dict)

    # Determine which columns to update on conflict.
    pk_columns = {col.key for col in model_class.__table__.primary_key.columns}
    if update_columns is None:
        conflict_keys = {name_to_key[c] for c in conflict_columns}
        excluded_cols = conflict_keys | pk_columns | {"create_ts", "update_ts"}
        update_columns = [col for col in model_columns if col not in excluded_cols]

    num_cols = len(model_class.__table__.columns)
    if _use_postgresql():
        # PostgreSQL's parameter limit is much higher (32767 by default for
        # the protocol). Use a generous chunk size.
        max_rows = max(1, 5000)
    else:
        max_rows = max(1, _SQLITE_MAX_PARAMS // num_cols)

    returned_rows: List[Dict[str, Any]] = []

    for chunk_start in range(0, len(values), max_rows):
        chunk = values[chunk_start : chunk_start + max_rows]

        if _use_postgresql():
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            insert_stmt = pg_insert(model_class).values(chunk)
        else:
            insert_stmt = sqlite_insert(model_class).values(chunk)

        if on_conflict_update:
            update_dict = {col: insert_stmt.excluded[col] for col in update_columns}

            if hasattr(model_class, "update_ts"):
                update_dict["update_ts"] = func.current_timestamp()

            if not update_dict:
                key_col = name_to_key[conflict_columns[0]]
                update_dict[key_col] = insert_stmt.excluded[key_col]

            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=conflict_columns, set_=update_dict
            )
        elif returning_columns:
            key_col = name_to_key[conflict_columns[0]]
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=conflict_columns,
                set_={key_col: insert_stmt.excluded[key_col]},
            )
        else:
            upsert_stmt = insert_stmt.on_conflict_do_nothing(
                index_elements=conflict_columns
            )

        if returning_columns:
            return_cols = [getattr(model_class, col) for col in returning_columns]
            upsert_stmt = upsert_stmt.returning(*return_cols)
            result = session.execute(upsert_stmt)
            returned_rows.extend(row._asdict() for row in result.fetchall())
        else:
            session.execute(upsert_stmt)

    if returning_columns is None:
        return model_instances
    return [model_class(**row) for row in returned_rows]
