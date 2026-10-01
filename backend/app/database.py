import sqlite3
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.config import APP_ENV, DATABASE_URL, PRODUCTION_ENVS

DATABASE_ERRORS = (sqlite3.Error, psycopg.Error)


class PostgresConnection:
    is_postgresql = True

    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, query, params=None):
        return self.connection.execute(query.replace("?", "%s"), params)


def get_connection():
    if DATABASE_URL.startswith("postgresql://"):
        return PostgresConnection(psycopg.connect(DATABASE_URL, row_factory=dict_row))

    if not DATABASE_URL.startswith("sqlite:///") or APP_ENV in PRODUCTION_ENVS:
        raise RuntimeError("SQLite connections are disabled in production")

    db_path = Path(DATABASE_URL.replace("sqlite:///", "", 1))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def verify_database_connection() -> None:
    required_schema = (
        "SELECT id, username, email, password_hash, api_token FROM users LIMIT 0",
        "SELECT id, user_id, query, results, workspace_id, created_at FROM searches LIMIT 0",
        "SELECT id, user_id, claim_text, status, workspace_id, created_at FROM claims LIMIT 0",
        "SELECT id, user_id, source_id, source_title, authors, year, doi, url, excerpt, evidence_type, relation, confidence, workspace_id, created_at FROM evidence LIMIT 0",
        "SELECT claim_id, evidence_id FROM claim_evidence LIMIT 0",
        "SELECT id, user_id, source_claim_id, target_claim_id, relation, workspace_id, created_at FROM claim_relations LIMIT 0",
        "SELECT id, user_id, title, research_question, notes, created_at, updated_at FROM research_workspaces LIMIT 0",
    )
    with get_connection() as conn:
        conn.execute("SELECT 1").fetchone()
        for query in required_schema:
            conn.execute(query).fetchall()


def insert_and_get_id(conn, query, params):
    if getattr(conn, "is_postgresql", False):
        query = f"{query.rstrip().rstrip(';')} RETURNING id"
        row = conn.execute(query, params).fetchone()
        if row is None:
            raise RuntimeError("INSERT did not return an id")
        return row["id"]
    return conn.execute(query, params).lastrowid


def is_integrity_error(error):
    return isinstance(error, (sqlite3.IntegrityError, psycopg.IntegrityError))


def init_db() -> None:
    if APP_ENV in PRODUCTION_ENVS:
        raise RuntimeError("Automatic database initialization is disabled in production")
    if not DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError("PostgreSQL schema changes must be applied explicitly")

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                api_token TEXT UNIQUE NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                results TEXT NOT NULL,
                workspace_id INTEGER REFERENCES research_workspaces(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                claim_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                workspace_id INTEGER REFERENCES research_workspaces(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source_id TEXT,
                source_title TEXT NOT NULL,
                authors TEXT NOT NULL DEFAULT '[]',
                year INTEGER,
                doi TEXT,
                url TEXT,
                excerpt TEXT,
                evidence_type TEXT NOT NULL,
                relation TEXT NOT NULL,
                confidence REAL,
                workspace_id INTEGER REFERENCES research_workspaces(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claim_evidence (
                claim_id INTEGER NOT NULL,
                evidence_id INTEGER NOT NULL,
                PRIMARY KEY (claim_id, evidence_id),
                FOREIGN KEY(claim_id) REFERENCES claims(id),
                FOREIGN KEY(evidence_id) REFERENCES evidence(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claim_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source_claim_id INTEGER NOT NULL,
                target_claim_id INTEGER NOT NULL,
                relation TEXT NOT NULL,
                workspace_id INTEGER REFERENCES research_workspaces(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(source_claim_id) REFERENCES claims(id),
                FOREIGN KEY(target_claim_id) REFERENCES claims(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                research_question TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        for table in ("searches", "claims", "evidence", "claim_relations"):
            existing_columns = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "workspace_id" not in existing_columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id INTEGER")
