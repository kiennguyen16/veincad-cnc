from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import bcrypt

from app.config import Settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utc_now().isoformat()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self, settings: Settings) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY,
                    folder_id TEXT,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    content_type TEXT,
                    upload_timestamp TEXT NOT NULL,
                    associated_user_id TEXT NOT NULL,
                    generated_job_id TEXT,
                    preview_path TEXT,
                    mask_path TEXT,
                    dxf_path TEXT,
                    FOREIGN KEY (folder_id) REFERENCES storage_folders(id) ON DELETE SET NULL,
                    FOREIGN KEY (associated_user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS storage_folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id TEXT,
                    owner_user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(owner_user_id, name, parent_id),
                    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES storage_folders(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS dxf_revisions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    action_summary TEXT NOT NULL,
                    dxf_path TEXT NOT NULL,
                    preview_path TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS dxf_messages (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS training_samples (
                    id TEXT PRIMARY KEY,
                    source_original_filename TEXT NOT NULL,
                    source_stored_filename TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    label_original_filename TEXT NOT NULL,
                    label_stored_filename TEXT NOT NULL,
                    label_path TEXT NOT NULL,
                    style_id TEXT NOT NULL CHECK (style_id IN ('centerline', 'high_detail')),
                    notes TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_training_samples_style
                    ON training_samples(style_id);
                CREATE INDEX IF NOT EXISTS idx_training_samples_created_at
                    ON training_samples(created_at DESC);
                """
            )
            existing = conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(?)",
                (settings.seed_admin_email,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO users (id, email, password_hash, role, created_at)
                    VALUES (?, ?, ?, 'admin', ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        settings.seed_admin_email.lower(),
                        hash_password(settings.seed_admin_password),
                        utc_iso(),
                    ),
                )
            self._ensure_schema(conn)
            for user in conn.execute("SELECT id FROM users").fetchall():
                default_folder = conn.execute(
                    "SELECT id FROM storage_folders WHERE owner_user_id = ? AND name = 'Default' AND parent_id IS NULL",
                    (user["id"],),
                ).fetchone()
                if default_folder is None:
                    conn.execute(
                        """
                        INSERT INTO storage_folders (id, name, parent_id, owner_user_id, created_at)
                        VALUES (?, 'Default', NULL, ?, ?)
                        """,
                        (uuid.uuid4().hex, user["id"], utc_iso()),
                    )

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        upload_columns = {row["name"] for row in conn.execute("PRAGMA table_info(uploads)").fetchall()}
        if "folder_id" not in upload_columns:
            conn.execute("ALTER TABLE uploads ADD COLUMN folder_id TEXT")

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return row_to_dict(
                conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
            )

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def create_user(self, *, email: str, password: str, role: str = "user") -> dict[str, Any]:
        user_id = uuid.uuid4().hex
        clean_email = email.strip().lower()
        if not clean_email:
            raise ValueError("Email is required.")
        if role not in {"user", "admin"}:
            raise ValueError("Unsupported user role.")

        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users (id, email, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, clean_email, hash_password(password), role, utc_iso()),
                )
                conn.execute(
                    """
                    INSERT INTO storage_folders (id, name, parent_id, owner_user_id, created_at)
                    VALUES (?, 'Default', NULL, ?, ?)
                    """,
                    (uuid.uuid4().hex, user_id, utc_iso()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("A user with this email already exists.") from exc

            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row)

    def admin_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            summary = {
                "user_count": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "active_session_count": conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE expires_at > ?",
                    (utc_iso(),),
                ).fetchone()[0],
                "upload_count": conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0],
                "folder_count": conn.execute("SELECT COUNT(*) FROM storage_folders").fetchone()[0],
                "dxf_revision_count": conn.execute("SELECT COUNT(*) FROM dxf_revisions").fetchone()[0],
                "dxf_message_count": conn.execute("SELECT COUNT(*) FROM dxf_messages").fetchone()[0],
            }
            latest_uploads = conn.execute(
                """
                SELECT
                    uploads.id,
                    uploads.original_filename,
                    storage_folders.name AS folder_name,
                    uploads.upload_timestamp,
                    uploads.associated_user_id,
                    users.email AS user_email,
                    uploads.generated_job_id
                FROM uploads
                JOIN users ON users.id = uploads.associated_user_id
                LEFT JOIN storage_folders ON storage_folders.id = uploads.folder_id
                ORDER BY uploads.upload_timestamp DESC
                LIMIT 10
                """
            ).fetchall()
            summary["latest_uploads"] = [dict(row) for row in latest_uploads]
            return summary

    def create_session(self, user_id: str, session_days: int) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(48)
        expires_at = utc_now() + timedelta(days=session_days)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (hash_session_token(token), user_id, utc_iso(), expires_at.isoformat()),
            )
        return token, expires_at

    def create_password_reset_token(self, *, user_id: str, expires_minutes: int) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(48)
        expires_at = utc_now() + timedelta(minutes=expires_minutes)
        with self.connect() as conn:
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
                (utc_iso(), user_id),
            )
            conn.execute(
                """
                INSERT INTO password_reset_tokens (token_hash, user_id, created_at, expires_at, used_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (hash_session_token(token), user_id, utc_iso(), expires_at.isoformat()),
            )
        return token, expires_at

    def reset_password_with_token(self, *, token: str, password: str) -> dict[str, Any] | None:
        token_hash = hash_session_token(token)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT users.*
                FROM password_reset_tokens
                JOIN users ON users.id = password_reset_tokens.user_id
                WHERE password_reset_tokens.token_hash = ?
                  AND password_reset_tokens.used_at IS NULL
                  AND password_reset_tokens.expires_at > ?
                """,
                (token_hash, utc_iso()),
            ).fetchone()
            if row is None:
                return None

            user = dict(row)
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user["id"]),
            )
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
                (utc_iso(), token_hash),
            )
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
            return user

    def get_user_for_session(self, token: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (hash_session_token(token), utc_iso()),
            ).fetchone()
            return row_to_dict(row)

    def delete_session(self, token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_session_token(token),))

    def record_upload(
        self,
        *,
        upload_id: str,
        folder_id: str | None,
        original_filename: str,
        stored_filename: str,
        file_path: Path,
        content_type: str | None,
        user_id: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO uploads (
                    id, folder_id, original_filename, stored_filename, file_path, content_type,
                    upload_timestamp, associated_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    folder_id,
                    original_filename,
                    stored_filename,
                    str(file_path),
                    content_type,
                    utc_iso(),
                    user_id,
                ),
            )

    def list_uploads(self, *, user_id: str, folder_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            params: list[Any] = [user_id]
            folder_clause = ""
            if folder_id:
                folder_clause = "AND uploads.folder_id = ?"
                params.append(folder_id)
            rows = conn.execute(
                f"""
                SELECT
                    uploads.id, uploads.folder_id, storage_folders.name AS folder_name,
                    original_filename, stored_filename, file_path, upload_timestamp,
                    associated_user_id, generated_job_id, preview_path, mask_path, dxf_path
                FROM uploads
                LEFT JOIN storage_folders ON storage_folders.id = uploads.folder_id
                WHERE associated_user_id = ?
                {folder_clause}
                ORDER BY upload_timestamp DESC
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def list_folders(self, *, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    storage_folders.id,
                    storage_folders.name,
                    storage_folders.parent_id,
                    storage_folders.owner_user_id,
                    storage_folders.created_at,
                    COUNT(uploads.id) AS upload_count
                FROM storage_folders
                LEFT JOIN uploads ON uploads.folder_id = storage_folders.id
                WHERE storage_folders.owner_user_id = ?
                GROUP BY storage_folders.id
                ORDER BY storage_folders.created_at ASC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_folder(self, *, user_id: str, name: str, parent_id: str | None = None) -> dict[str, Any]:
        folder_id = uuid.uuid4().hex
        clean_name = " ".join(name.strip().split())
        if not clean_name:
            raise ValueError("Folder name is required.")
        with self.connect() as conn:
            if parent_id:
                parent = conn.execute(
                    "SELECT id FROM storage_folders WHERE id = ? AND owner_user_id = ?",
                    (parent_id, user_id),
                ).fetchone()
                if parent is None:
                    raise ValueError("Parent folder not found.")
            conn.execute(
                """
                INSERT INTO storage_folders (id, name, parent_id, owner_user_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (folder_id, clean_name, parent_id, user_id, utc_iso()),
            )
            row = conn.execute("SELECT * FROM storage_folders WHERE id = ?", (folder_id,)).fetchone()
            return dict(row)

    def get_folder(self, *, folder_id: str, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return row_to_dict(
                conn.execute(
                    "SELECT * FROM storage_folders WHERE id = ? AND owner_user_id = ?",
                    (folder_id, user_id),
                ).fetchone()
            )

    def default_folder_id(self, *, user_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM storage_folders WHERE owner_user_id = ? AND name = 'Default' AND parent_id IS NULL",
                (user_id,),
            ).fetchone()
            return str(row["id"]) if row else None

    def attach_upload_job(
        self,
        *,
        upload_id: str,
        job_id: str,
        preview_path: str,
        mask_path: str,
        dxf_path: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE uploads
                SET generated_job_id = ?, preview_path = ?, mask_path = ?, dxf_path = ?
                WHERE id = ?
                """,
                (job_id, preview_path, mask_path, dxf_path, upload_id),
            )

    def record_dxf_message(self, *, job_id: str, user_id: str, role: str, content: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dxf_messages (id, job_id, user_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, job_id, user_id, role, content, utc_iso()),
            )

    def record_dxf_revision(
        self,
        *,
        revision_id: str,
        job_id: str,
        user_id: str,
        prompt: str,
        action_summary: str,
        dxf_path: Path,
        preview_path: Path | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dxf_revisions (
                    id, job_id, user_id, prompt, action_summary, dxf_path, preview_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    job_id,
                    user_id,
                    prompt,
                    action_summary,
                    str(dxf_path),
                    str(preview_path) if preview_path else None,
                    utc_iso(),
                ),
            )

    def list_dxf_messages(self, *, job_id: str, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM dxf_messages
                WHERE job_id = ? AND user_id = ?
                ORDER BY created_at ASC
                """,
                (job_id, user_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def latest_dxf_revision(self, *, job_id: str, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return row_to_dict(
                conn.execute(
                    """
                    SELECT *
                    FROM dxf_revisions
                    WHERE job_id = ? AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (job_id, user_id),
                ).fetchone()
            )

    def create_training_sample(
        self,
        *,
        sample_id: str,
        source_original_filename: str,
        source_stored_filename: str,
        source_path: str,
        label_original_filename: str,
        label_stored_filename: str,
        label_path: str,
        style_id: str,
        notes: str | None,
        status: str,
        created_by: str,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO training_samples (
                    id,
                    source_original_filename,
                    source_stored_filename,
                    source_path,
                    label_original_filename,
                    label_stored_filename,
                    label_path,
                    style_id,
                    notes,
                    status,
                    created_at,
                    created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample_id,
                    source_original_filename,
                    source_stored_filename,
                    source_path,
                    label_original_filename,
                    label_stored_filename,
                    label_path,
                    style_id,
                    notes,
                    status,
                    utc_iso(),
                    created_by,
                ),
            )
            row = conn.execute(
                """
                SELECT training_samples.*, users.email AS created_by_email
                FROM training_samples
                JOIN users ON users.id = training_samples.created_by
                WHERE training_samples.id = ?
                """,
                (sample_id,),
            ).fetchone()
            return dict(row)

    def get_training_sample(self, *, sample_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return row_to_dict(
                conn.execute(
                    """
                    SELECT training_samples.*, users.email AS created_by_email
                    FROM training_samples
                    JOIN users ON users.id = training_samples.created_by
                    WHERE training_samples.id = ?
                    """,
                    (sample_id,),
                ).fetchone()
            )

    def list_training_samples(self, *, style_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            params: tuple[Any, ...] = ()
            style_clause = ""
            if style_id is not None:
                style_clause = "WHERE training_samples.style_id = ?"
                params = (style_id,)
            rows = conn.execute(
                f"""
                SELECT training_samples.*, users.email AS created_by_email
                FROM training_samples
                JOIN users ON users.id = training_samples.created_by
                {style_clause}
                ORDER BY training_samples.created_at DESC
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def training_sample_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT style_id, COUNT(*) AS sample_count
                FROM training_samples
                GROUP BY style_id
                """
            ).fetchall()
            return {str(row["style_id"]): int(row["sample_count"]) for row in rows}

    def delete_training_sample(self, *, sample_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM training_samples WHERE id = ?", (sample_id,))
            return cursor.rowcount > 0
