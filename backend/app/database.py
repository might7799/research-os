import sqlite3
from pathlib import Path

import psycopg

from app.config import DATABASE_URL


def get_connection():
    if DATABASE_URL.startswith("postgresql"):
        return psycopg.connect(DATABASE_URL)

    db_path = Path(DATABASE_URL.replace("sqlite:///", "", 1))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        if DATABASE_URL.startswith("postgresql"):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
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
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    results TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS claims (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    claim_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence (
                    id SERIAL PRIMARY KEY,
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_evidence (
                    claim_id INTEGER NOT NULL,
                    evidence_id INTEGER NOT NULL,
                    PRIMARY KEY (claim_id, evidence_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_relations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    source_claim_id INTEGER NOT NULL,
                    target_claim_id INTEGER NOT NULL,
                    relation TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_workspaces (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    research_question TEXT NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for table in ("searches", "claims", "evidence", "claim_relations"):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS workspace_id INTEGER")
            return

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
