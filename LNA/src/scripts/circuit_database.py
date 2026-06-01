from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from pathlib import Path


SCHEMA_VERSION = 3
DEFAULT_CIRCUIT_DATABASE_PATH = Path("data/circuit_database/circuits.sqlite")
KEY_NETLIST_PARAMETERS = (
    "corner",
    "process_lib_path",
    "temperature_c",
    "f0",
    "vdd",
    "ac_start",
    "ac_stop",
)
NETWORK_ROLES = ("gate", "source", "load", "feedback")
RLC_AXES = ("r", "l", "c")


def canonical_json(payload):
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_number(value):
    number = float(value)
    if not math.isfinite(number):
        return str(value)
    if number == 0.0:
        number = 0.0
    return f"{number:.12g}"


def normalize_for_signature(value):
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return canonical_number(value)
    if isinstance(value, list):
        return [normalize_for_signature(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_for_signature(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): normalize_for_signature(value[key])
            for key in sorted(value)
        }
    return str(value)


def netlist_context_from_config(config):
    parameters = (config or {}).get("netlist_parameters") or {}
    return {
        key: parameters[key]
        for key in KEY_NETLIST_PARAMETERS
        if key in parameters
    }


def network_signature(network):
    if not isinstance(network, dict):
        return {"identifier": None, "passive_indexes": None}

    passive_indexes = network.get("passive_indexes")
    if isinstance(passive_indexes, dict):
        passive_indexes = {
            axis: int(passive_indexes.get(axis, 0))
            for axis in RLC_AXES
        }
    else:
        passive_indexes = None

    return {
        "identifier": network.get("identifier"),
        "passive_indexes": passive_indexes,
    }


def circuit_signature(candidate, netlist_context=None):
    transistor_parameters = candidate.get("transistor_parameters") or {}
    networks = candidate.get("networks") or {}
    signature = {
        "schema": "lna_circuit_signature",
        "schema_version": SCHEMA_VERSION,
        "netlist": netlist_context or {},
        "transistor": {
            "name": candidate.get("transistor"),
            "device_type": transistor_parameters.get("device_type"),
            "threshold": transistor_parameters.get("threshold"),
            "wtot_um": transistor_parameters.get("wtot_um"),
            "length_um": transistor_parameters.get("length_um"),
            "m": transistor_parameters.get("m"),
            "unit_width_um": transistor_parameters.get("unit_width_um"),
        },
        "vg": candidate.get("vg"),
        "networks": {
            role: network_signature(networks.get(role))
            for role in NETWORK_ROLES
        },
    }
    return normalize_for_signature(signature)


def circuit_key(candidate, netlist_context=None):
    signature = circuit_signature(candidate, netlist_context)
    signature_json = canonical_json(signature)
    digest = hashlib.sha256(signature_json.encode("utf-8")).hexdigest()
    return digest, signature, signature_json


def metrics_priority(metrics):
    return -len(metrics or {})


def source_record_key(
    *,
    circuit_key,
    metrics_json,
    source_evaluation_id,
    source_circuit_dir,
    created_at_unix,
):
    payload = {
        "circuit_key": circuit_key,
        "created_at_unix": normalize_for_signature(created_at_unix),
        "metrics": json.loads(metrics_json),
        "source_circuit_dir": source_circuit_dir,
        "source_evaluation_id": source_evaluation_id,
    }
    payload_json = canonical_json(normalize_for_signature(payload))
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _table_columns(conn, table_name):
    columns = set()
    for row in conn.execute(f"PRAGMA table_info({table_name})"):
        columns.add(row["name"] if isinstance(row, sqlite3.Row) else row[1])
    return columns


def _ensure_column(conn, table_name, column_name, column_definition):
    if column_name in _table_columns(conn, table_name):
        return
    conn.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )


def _backfill_source_record_keys(conn):
    rows = conn.execute(
        """
        SELECT
            circuit_sources.id,
            circuit_sources.circuit_key,
            circuit_sources.source_evaluation_id,
            circuit_sources.source_circuit_dir,
            circuit_sources.created_at_unix,
            circuits.metrics_json
        FROM circuit_sources
        JOIN circuits ON circuits.circuit_key = circuit_sources.circuit_key
        WHERE circuit_sources.source_record_key IS NULL
        """
    ).fetchall()
    for row in rows:
        key = source_record_key(
            circuit_key=row["circuit_key"],
            metrics_json=row["metrics_json"],
            source_evaluation_id=row["source_evaluation_id"],
            source_circuit_dir=row["source_circuit_dir"],
            created_at_unix=row["created_at_unix"],
        )
        conn.execute(
            """
            UPDATE circuit_sources
            SET source_record_key = ?
            WHERE id = ?
            """,
            (key, row["id"]),
        )


def initialize_database(conn):
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS circuits (
            circuit_key TEXT PRIMARY KEY,
            key_schema_version INTEGER NOT NULL,
            signature_json TEXT NOT NULL,
            genome_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            candidate_json TEXT NOT NULL,
            source_run TEXT,
            source_history TEXT,
            source_evaluation_id INTEGER,
            source_circuit_dir TEXT,
            created_at_unix REAL,
            duplicate_count INTEGER NOT NULL DEFAULT 1,
            imported_at_unix REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS circuit_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            circuit_key TEXT NOT NULL,
            source_run TEXT NOT NULL,
            source_history TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            source_evaluation_id INTEGER,
            source_circuit_dir TEXT,
            created_at_unix REAL,
            source_record_key TEXT,
            FOREIGN KEY(circuit_key) REFERENCES circuits(circuit_key)
        )
        """
    )
    _ensure_column(
        conn,
        "circuit_sources",
        "source_record_key",
        "TEXT",
    )
    _backfill_source_record_keys(conn)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sources_key
        ON circuit_sources(circuit_key)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sources_record_key
        ON circuit_sources(source_record_key)
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO metadata(key, value)
        VALUES('schema_version', ?)
        """,
        (str(SCHEMA_VERSION),),
    )


def entry_from_row(row):
    if row is None:
        return None
    return {
        "circuit_key": row["circuit_key"],
        "signature": json.loads(row["signature_json"]),
        "genome": json.loads(row["genome_json"]),
        "candidate": json.loads(row["candidate_json"]),
        "metrics": json.loads(row["metrics_json"]),
        "source_run": row["source_run"],
        "source_history": row["source_history"],
        "source_evaluation_id": row["source_evaluation_id"],
        "source_circuit_dir": row["source_circuit_dir"],
        "created_at_unix": row["created_at_unix"],
        "duplicate_count": row["duplicate_count"],
    }


def upsert_history_record(
    conn,
    record,
    *,
    netlist_context,
    source_run,
    source_history,
    source_line,
):
    candidate = record.get("candidate")
    if not isinstance(candidate, dict):
        return None
    metrics = record.get("metrics") or {}
    if not metrics:
        return None

    key, _, signature_json = circuit_key(candidate, netlist_context)
    now = time.time()
    genome_json = canonical_json(record.get("genome") or [])
    metrics_json = canonical_json(metrics)
    candidate_json = canonical_json(candidate)
    evaluation_id = record.get("evaluation_id")
    circuit_dir = record.get("circuit_dir")
    created_at_unix = record.get("created_at_unix")
    record_key = source_record_key(
        circuit_key=key,
        metrics_json=metrics_json,
        source_evaluation_id=evaluation_id,
        source_circuit_dir=circuit_dir,
        created_at_unix=created_at_unix,
    )

    existing_source = conn.execute(
        """
        SELECT id
        FROM circuit_sources
        WHERE source_record_key = ?
        LIMIT 1
        """,
        (record_key,),
    ).fetchone()
    if existing_source is not None:
        return {
            "circuit_key": key,
            "new_circuit": False,
            "source_inserted": False,
            "already_imported": True,
        }

    existing = conn.execute(
        "SELECT metrics_json FROM circuits WHERE circuit_key = ?",
        (key,),
    ).fetchone()
    new_circuit = existing is None
    if existing is None:
        conn.execute(
            """
            INSERT INTO circuits(
                circuit_key,
                key_schema_version,
                signature_json,
                genome_json,
                metrics_json,
                candidate_json,
                source_run,
                source_history,
                source_evaluation_id,
                source_circuit_dir,
                created_at_unix,
                duplicate_count,
                imported_at_unix
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                key,
                SCHEMA_VERSION,
                signature_json,
                genome_json,
                metrics_json,
                candidate_json,
                source_run,
                source_history,
                evaluation_id,
                circuit_dir,
                created_at_unix,
                now,
            ),
        )
    else:
        existing_metrics = json.loads(existing["metrics_json"])
        if metrics_priority(metrics) < metrics_priority(existing_metrics):
            conn.execute(
                """
                UPDATE circuits
                SET genome_json = ?,
                    metrics_json = ?,
                    candidate_json = ?,
                    source_run = ?,
                    source_history = ?,
                    source_evaluation_id = ?,
                    source_circuit_dir = ?,
                    created_at_unix = ?,
                    duplicate_count = duplicate_count + 1
                WHERE circuit_key = ?
                """,
                (
                    genome_json,
                    metrics_json,
                    candidate_json,
                    source_run,
                    source_history,
                    evaluation_id,
                    circuit_dir,
                    created_at_unix,
                    key,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE circuits
                SET duplicate_count = duplicate_count + 1
                WHERE circuit_key = ?
                """,
                (key,),
            )

    conn.execute(
        """
        INSERT INTO circuit_sources(
            circuit_key,
            source_run,
            source_history,
            source_line,
            source_evaluation_id,
            source_circuit_dir,
            created_at_unix,
            source_record_key
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            source_run,
            source_history,
            source_line,
            evaluation_id,
            circuit_dir,
            created_at_unix,
            record_key,
        ),
    )
    return {
        "circuit_key": key,
        "new_circuit": new_circuit,
        "source_inserted": True,
        "already_imported": False,
    }


class CircuitDatabase:
    def __init__(self, path=DEFAULT_CIRCUIT_DATABASE_PATH):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()

    def close(self):
        with self._lock:
            self.conn.close()

    def lookup(self, candidate, netlist_context=None):
        key, _, _ = circuit_key(candidate, netlist_context)
        return self.lookup_by_key(key)

    def lookup_metrics(self, candidate, netlist_context=None):
        entry = self.lookup(candidate, netlist_context)
        if entry is None:
            return None
        return entry["metrics"]

    def lookup_by_key(self, key):
        with self._lock:
            row = self.conn.execute(
                """
                SELECT
                    circuit_key,
                    signature_json,
                    genome_json,
                    candidate_json,
                    metrics_json,
                    source_run,
                    source_history,
                    source_evaluation_id,
                    source_circuit_dir,
                    created_at_unix,
                    duplicate_count
                FROM circuits
                WHERE circuit_key = ?
                """,
                (key,),
            ).fetchone()
        return entry_from_row(row)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
