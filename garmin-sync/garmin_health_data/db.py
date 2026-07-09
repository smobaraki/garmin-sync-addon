"""
Database initialization and management for garmin-health-data.

Handles both SQLite and PostgreSQL database creation, session management, and query
utilities. When ``DATABASE_URL`` is set in the environment and contains a PostgreSQL
connection string, the engine connects to that database. Otherwise the tool defaults to
a local SQLite file.
"""

import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import click
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

# Handle importlib.resources for different Python versions
if sys.version_info >= (3, 9):
    from importlib.resources import files
else:
    from importlib_resources import files

from garmin_health_data.models import (
    Activity,
    Base,
    BodyBattery,
    Floors,
    HeartRate,
    IntensityMinutes,
    Respiration,
    Sleep,
    Steps,
    Stress,
    TrainingReadiness,
    User,
)

_MIN_SQLITE_VERSION = (3, 35, 0)


def _add_missing_columns(engine) -> None:
    """
    Add columns present on the ORM models but missing from existing tables.

    ``Base.metadata.create_all`` only creates whole missing tables; it never adds
    new columns to a table that already exists. When a model gains a column (e.g.
    the ``nap`` table's ``body_battery_impact`` / ``short_feedback`` additions),
    existing databases would be missing it and inserts would fail. This performs a
    best-effort additive ``ALTER TABLE ... ADD COLUMN`` for each missing column,
    rolling back individually on error (e.g. a NOT NULL column without a default on
    a populated table). Only additive; never drops or alters existing columns.

    :param engine: SQLAlchemy engine bound to the target database.
    """
    from sqlalchemy import inspect as sqla_inspect

    insp = sqla_inspect(engine)
    existing_tables = set(insp.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # Brand-new tables are handled by create_all.
        existing_cols = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            try:
                col_type = col.type.compile(dialect=engine.dialect)
            except Exception:
                continue
            ddl = (
                f'ALTER TABLE "{table.name}" '
                f'ADD COLUMN "{col.name}" {col_type}'
            )
            with engine.connect() as conn:
                try:
                    conn.execute(text(ddl))
                    conn.commit()
                except Exception:
                    conn.rollback()



def _detect_database_url() -> Optional[str]:
    """
    Return the ``DATABASE_URL`` environment variable if set, else None.

    :return: Database URL string or None.
    """
    return os.environ.get("DATABASE_URL")


def _is_postgresql(url: str) -> bool:
    """
    Return True when the URL starts with ``postgresql://`` or ``postgres://``.

    :param url: Database URL string.
    :return: True if the URL targets a PostgreSQL database.
    """
    return url.startswith("postgresql://") or url.startswith("postgres://")


def check_sqlite_version() -> None:
    """
    Validate that the linked SQLite library meets the minimum required version.

    :raises RuntimeError: If the installed SQLite version is too old.
    """
    if sqlite3.sqlite_version_info < _MIN_SQLITE_VERSION:
        required = ".".join(str(v) for v in _MIN_SQLITE_VERSION)
        raise RuntimeError(
            f"garmin-health-data requires SQLite >= {required} "
            f"(found {sqlite3.sqlite_version}). "
            "Upgrade your Python build or system SQLite library."
        )


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """
    Enable SQLite foreign-key enforcement on every new connection.

    SQLite defaults ``PRAGMA foreign_keys`` to OFF per connection, so ``ON DELETE
    CASCADE`` clauses in the schema are silently inert without this. Registered as a
    SQLAlchemy ``connect`` event listener on engines created by :func:`get_engine`.

    :param dbapi_connection: DB-API connection instance (sqlite3.Connection).
    :param _connection_record: SQLAlchemy connection record (unused).
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def get_engine(db_path: str = "garmin_data.db"):
    """
    Create SQLAlchemy engine for the database.

    When ``DATABASE_URL`` is set in the environment it is used as the connection URL
    (supporting PostgreSQL and other dialects). Otherwise a local SQLite file is used.

    For PostgreSQL, ``pool_pre_ping=True`` is set so stale connections (e.g. after an
    idle period on a cloud host) are detected and replaced transparently.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    :return: SQLAlchemy engine.
    """
    env_url = _detect_database_url()
    if env_url:
        # Normalize postgres:// to postgresql:// for SQLAlchemy 2.x
        # (Heroku, Neon, Supabase, and some older tooling still emit
        # postgres:// URLs).
        if env_url.startswith("postgres://"):
            env_url = env_url.replace("postgres://", "postgresql://", 1)
        if _is_postgresql(env_url):
            engine = create_engine(
                env_url,
                echo=False,
                pool_pre_ping=True,
            )
        else:
            engine = create_engine(env_url, echo=False)
        return engine

    check_sqlite_version()
    db_file = Path(db_path).expanduser().resolve()
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    return engine


def _split_sql_statements(sql: str):
    """Split SQL into statements, respecting single-quoted strings."""
    stmts = []
    current = []
    i = 0
    n = len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            current.append(c)
            i += 1
            while i < n:
                c2 = sql[i]
                current.append(c2)
                if c2 == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        current.append("'")
                        i += 2
                        continue
                    else:
                        i += 1
                        break
                i += 1
        elif c == ";":
            stmt = "".join(current).strip()
            if stmt:
                stmts.append(stmt)
            current = []
            i += 1
        else:
            current.append(c)
            i += 1
    stmt = "".join(current).strip()
    if stmt:
        stmts.append(stmt)
    return stmts


def _execute_ddl_on_postgresql(engine) -> None:
    """
    Create all tables on a PostgreSQL database using the native DDL file.

    Uses ``tables_postgres.ddl`` which contains PostgreSQL-native types
    (``SERIAL``, ``TIMESTAMPTZ``, proper ``ON DELETE CASCADE``, etc.).

    :param engine: SQLAlchemy engine connected to PostgreSQL.
    """
    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        except Exception:
            pass

    ddl_file = Path(__file__).parent / "tables_postgres.ddl"
    if not ddl_file.exists():
        raise FileNotFoundError(f"PostgreSQL DDL file not found: {ddl_file}")
    ddl_sql = ddl_file.read_text()
    ddl_sql = re.sub(r'/\*.*?\*/', '', ddl_sql, flags=re.DOTALL)
    ddl_sql = re.sub(r'--[^\n]*', '', ddl_sql)

    with engine.connect() as conn:
        statements = _split_sql_statements(ddl_sql)
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--") or stmt.startswith("/*"):
                continue
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                conn.rollback()

    # Run create_all() as a fallback for any tables not in the
    # tables_postgres.ddl (e.g. tables added after the openetl DDL was
    # last synced: menstrual_cycle_*, body_composition, strength_*,
    # activity_path, activity_ts_metric_downsampled, etc.). Because
    # the core DDL already created the shared tables, create_all()
    # only touches tables that do not yet exist.
    Base.metadata.create_all(engine)

    # Add any columns that models gained after their table was first created
    # (create_all never alters existing tables).
    _add_missing_columns(engine)

    # Reset SERIAL sequences for tables that may have been populated
    # before their auto-increment column was correctly defined. Without
    # this, new INSERTs without an explicit PK value collide with
    # existing rows because the sequence starts at 1.
    #
    # Step 1: add IDENTITY if the column was created as bare INTEGER
    # (from earlier Base.metadata.create_all() runs).  First drop any
    # leftover SERIAL default / sequence so the ALTER succeeds on
    # databases migrated from old SERIAL-based DDL.
    _fix_identity_columns = {
        "user_profile": "user_profile_id",
        "sleep": "sleep_id",
    }
    for table_name, col_name in _fix_identity_columns.items():
        with engine.connect() as c:
            try:
                c.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ALTER COLUMN "{col_name}" DROP DEFAULT'
                    )
                )
                c.commit()
            except Exception:
                c.rollback()
            try:
                c.execute(
                    text(
                        f'DROP SEQUENCE IF EXISTS '
                        f'{table_name}_{col_name}_seq'
                    )
                )
                c.commit()
            except Exception:
                c.rollback()
            try:
                c.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ALTER COLUMN "{col_name}" '
                        "ADD GENERATED BY DEFAULT AS IDENTITY"
                    )
                )
                c.commit()
            except Exception:
                c.rollback()

    # Step 2: set the sequence to max(id) + 1 so the next insert
    # starts after the existing rows.
    for table_name, col_name in _fix_identity_columns.items():
        with engine.connect() as c:
            try:
                result = c.execute(
                    text(f'SELECT max("{col_name}") FROM "{table_name}"')
                ).scalar()
                if result is not None:
                    c.execute(
                        text(
                            f"SELECT setval("
                            f"pg_get_serial_sequence('{table_name}', '{col_name}'), "
                            f"{result}"
                            f")"
                        )
                    )
                    c.commit()
            except Exception:
                c.rollback()


def create_tables(db_path: str = "garmin_data.db") -> None:
    """
    Create all tables in the database.

    For PostgreSQL (when ``DATABASE_URL`` is set), uses SQLAlchemy's
    ``Base.metadata.create_all()`` to generate DDL from the ORM models. For SQLite,
    executes the packaged ``tables.ddl`` file which includes inline comments preserved
    in the database.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    """
    env_url = _detect_database_url()
    if env_url and _is_postgresql(env_url):
        engine = get_engine(db_path)
        try:
            _execute_ddl_on_postgresql(engine)
        finally:
            engine.dispose()
        return

    check_sqlite_version()

    try:
        ddl_sql = files("garmin_health_data").joinpath("tables.ddl").read_text()
    except (FileNotFoundError, TypeError):
        ddl_file = Path(__file__).parent / "tables.ddl"
        if not ddl_file.exists():
            raise FileNotFoundError(f"Schema DDL file not found: {ddl_file}")
        ddl_sql = ddl_file.read_text()

    db_file = Path(db_path).expanduser()
    conn = sqlite3.connect(str(db_file))
    try:
        conn.executescript(ddl_sql)
        conn.commit()
    finally:
        conn.close()

    # Create any tables added after tables.ddl was last synced (e.g. gear, nap,
    # body_battery_event, daily_summary, hrv_daily, ...). create_all is
    # idempotent and only creates tables that do not yet exist, mirroring the
    # PostgreSQL path. Without this, SQLite databases are missing every table
    # added since the DDL file was last regenerated, causing inserts to fail.
    engine = get_engine(db_path)
    try:
        Base.metadata.create_all(engine)
        _add_missing_columns(engine)
    finally:
        engine.dispose()


@contextmanager
def get_session(db_path: str = "garmin_data.db"):
    """
    Context manager for database sessions.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    :yield: SQLAlchemy Session.
    """
    engine = get_engine(db_path)
    session = Session(engine)

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize_database(db_path: str = "garmin_data.db") -> None:
    """
    Initialize a new database with all tables and indexes.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    """
    env_url = _detect_database_url()
    if env_url:
        if _is_postgresql(env_url):
            click.echo(f"Initializing database at: {env_url}")
            # Hide the password portion of the URL in log output.
            safe_url = _redact_password(env_url)
            click.echo(f"Connection: {safe_url}")
        else:
            click.echo(f"Initializing database at: {env_url}")
    else:
        db_file = Path(db_path).expanduser()
        if db_file.exists():
            click.echo(f"Database already exists at: {db_file}")
        else:
            click.echo(f"Creating new database at: {db_file}")

    create_tables(db_path)
    click.secho("✅ Database initialized successfully", fg="green")

    if not (_detect_database_url() and _is_postgresql(_detect_database_url())):
        db_file = Path(db_path).expanduser()
        click.echo(
            "\nSchema includes inline documentation. To view table definitions:\n"
            f"  sqlite3 {db_file} "
            "\"SELECT sql FROM sqlite_master WHERE type='table';\""
        )


def _redact_password(url: str) -> str:
    """
    Replace the password portion of a database URL with ``***``.

    :param url: Database connection URL.
    :return: URL with password redacted.
    """
    import re

    return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", url)


def get_last_update_dates(db_path: str = "garmin_data.db") -> Dict[str, Optional[date]]:
    """
    Get the last update date for each data type.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    :return: Dictionary mapping data type name to last update date.
    """
    with get_session(db_path) as session:
        dates = {}

        last_sleep = session.execute(select(func.max(Sleep.start_ts))).scalar()
        dates["sleep"] = last_sleep.date() if last_sleep else None

        last_hr = session.execute(select(func.max(HeartRate.timestamp))).scalar()
        dates["heart_rate"] = last_hr.date() if last_hr else None

        last_activity = session.execute(select(func.max(Activity.start_ts))).scalar()
        dates["activity"] = last_activity.date() if last_activity else None

        last_stress = session.execute(select(func.max(Stress.timestamp))).scalar()
        dates["stress"] = last_stress.date() if last_stress else None

        last_bb = session.execute(select(func.max(BodyBattery.timestamp))).scalar()
        dates["body_battery"] = last_bb.date() if last_bb else None

        last_steps = session.execute(select(func.max(Steps.timestamp))).scalar()
        dates["steps"] = last_steps.date() if last_steps else None

        last_resp = session.execute(select(func.max(Respiration.timestamp))).scalar()
        dates["respiration"] = last_resp.date() if last_resp else None

        last_floors = session.execute(select(func.max(Floors.timestamp))).scalar()
        dates["floors"] = last_floors.date() if last_floors else None

        last_im = session.execute(select(func.max(IntensityMinutes.timestamp))).scalar()
        dates["intensity_minutes"] = last_im.date() if last_im else None

        last_tr = session.execute(
            select(func.max(TrainingReadiness.timestamp))
        ).scalar()
        dates["training_readiness"] = last_tr.date() if last_tr else None

        return dates


def get_latest_date(db_path: str = "garmin_data.db") -> Optional[date]:
    """
    Get the most recent date across all data types.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    :return: Most recent date or None if database is empty.
    """
    dates = get_last_update_dates(db_path)
    valid_dates = [d for d in dates.values() if d is not None]

    if not valid_dates:
        return None

    return max(valid_dates)


def get_record_counts(db_path: str = "garmin_data.db") -> Dict[str, int]:
    """
    Get record counts for all major tables.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    :return: Dictionary mapping table name to record count.
    """
    with get_session(db_path) as session:
        counts = {}

        counts["users"] = session.execute(select(func.count(User.user_id))).scalar()
        counts["activities"] = session.execute(
            select(func.count(Activity.activity_id))
        ).scalar()
        counts["sleep_sessions"] = session.execute(
            select(func.count(Sleep.sleep_id))
        ).scalar()
        counts["heart_rate_readings"] = session.execute(
            select(func.count(HeartRate.timestamp))
        ).scalar()
        counts["stress_readings"] = session.execute(
            select(func.count(Stress.timestamp))
        ).scalar()
        counts["body_battery_readings"] = session.execute(
            select(func.count(BodyBattery.timestamp))
        ).scalar()
        counts["step_readings"] = session.execute(
            select(func.count(Steps.timestamp))
        ).scalar()
        counts["respiration_readings"] = session.execute(
            select(func.count(Respiration.timestamp))
        ).scalar()

        return counts


def get_database_size(db_path: str = "garmin_data.db") -> int:
    """
    Get size of database in bytes.

    For SQLite, returns the file size. For PostgreSQL, returns an estimate based on the
    ``pg_database_size()`` function.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    :return: Size in bytes, or 0 if not available.
    """
    env_url = _detect_database_url()
    if env_url and _is_postgresql(env_url):
        with get_session(db_path) as session:
            try:
                result = session.execute(
                    text("SELECT pg_database_size(current_database())")
                ).scalar()
                return int(result) if result else 0
            except Exception:
                return 0

    db_file = Path(db_path).expanduser()
    if not db_file.exists():
        return 0
    return db_file.stat().st_size


def database_exists(db_path: str = "garmin_data.db") -> bool:
    """
    Check if database exists.

    For PostgreSQL (``DATABASE_URL``), always returns True  the caller is expected to
    have a valid URL; schema creation is idempotent via ``CREATE TABLE IF NOT EXISTS``.

    :param db_path: Path to SQLite database file (ignored when ``DATABASE_URL`` is set).
    :return: True if database exists, False otherwise.
    """
    env_url = _detect_database_url()
    if env_url and _is_postgresql(env_url):
        try:
            engine = get_engine(db_path)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return True

    db_file = Path(db_path).expanduser()
    return db_file.exists()
