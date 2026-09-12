"""分片上传会话的 SQLite 仓储。

本模块提供 :class:`UploadSessionRepository`，将会话元数据与分片
记录持久化到 SQLite。数据库使用 WAL 日志模式，支持多 worker
共享读写；所有写操作在单条 SQL 中完成，避免应用层锁竞争。

路径与 ID 均通过参数化查询写入，禁止字符串拼接；分片记录表通过
外键级联删除，会话删除时分片记录自动清理。
"""

import sqlite3
from pathlib import Path
from typing import Optional

from app.constants import (
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_COMPLETING,
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_UPLOADING,
)
from app.errors import BusinessError, ErrorCode
from app.models.upload_session import (
    UploadChunkRecord,
    UploadSession,
    UploadSessionSnapshot,
)


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS upload_sessions (
        upload_id TEXT PRIMARY KEY,
        target_path TEXT NOT NULL,
        size INTEGER NOT NULL,
        chunk_size INTEGER NOT NULL,
        total_chunks INTEGER NOT NULL,
        overwrite INTEGER NOT NULL,
        checksum_algorithm TEXT,
        checksum_value TEXT,
        status TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        expires_at REAL NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_upload_sessions_expires_at
        ON upload_sessions (expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_upload_sessions_status
        ON upload_sessions (status)
    """,
    """
    CREATE TABLE IF NOT EXISTS upload_chunks (
        upload_id TEXT NOT NULL,
        chunk_number INTEGER NOT NULL,
        received_size INTEGER NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (upload_id, chunk_number),
        FOREIGN KEY (upload_id)
            REFERENCES upload_sessions (upload_id)
            ON DELETE CASCADE
    )
    """,
)
"""建表与建索引的 SQL 语句集合，均使用 IF NOT EXISTS 以便幂等。"""


SESSION_COLUMNS: str = (
    "upload_id, target_path, size, chunk_size, total_chunks, "
    "overwrite, checksum_algorithm, checksum_value, status, "
    "created_at, updated_at, expires_at"
)
"""会话查询使用的列清单，保持 SELECT 语句整洁。"""


ACTIVE_STATUS_SQL: str = (
    f"'{STATUS_CREATED}', '{STATUS_UPLOADING}', '{STATUS_COMPLETING}'"
)
"""活动状态子句，供并发会话数统计与清理查询复用。"""


class UploadSessionRepository:
    """分片上传会话的 SQLite 仓储。

    Attributes:
        database_path: SQLite 数据库文件路径。
    """

    def __init__(self, database_path: Path) -> None:
        """构造仓储并初始化数据库结构。

        Args:
            database_path: SQLite 数据库文件路径。
        """
        self._database_path: Path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    @property
    def database_path(self) -> Path:
        """返回底层数据库文件路径。

        Returns:
            数据库文件路径。
        """
        return self._database_path

    def create_session(self, session: UploadSession) -> None:
        """持久化一个新的上传会话。

        Args:
            session: 会话对象。

        Raises:
            BusinessError: 会话 ID 已存在。
        """
        connection = self._connect()
        try:
            connection.execute(
                f"""
                INSERT INTO upload_sessions ({SESSION_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.upload_id,
                    session.target_path,
                    session.size,
                    session.chunk_size,
                    session.total_chunks,
                    int(session.overwrite),
                    session.checksum_algorithm,
                    session.checksum_value,
                    session.status,
                    session.created_at,
                    session.updated_at,
                    session.expires_at,
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise BusinessError(
                ErrorCode.CONFLICT,
                f"上传会话 ID 已存在：{session.upload_id}",
            ) from exc
        finally:
            connection.close()

    def get_session(self, upload_id: str) -> Optional[UploadSession]:
        """按 ID 读取会话。

        Args:
            upload_id: 会话 ID。

        Returns:
            会话对象；不存在时返回 ``None``。
        """
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT {SESSION_COLUMNS} FROM upload_sessions "
                f"WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return self._row_to_session(row)

    def get_snapshot(
        self, upload_id: str
    ) -> Optional[UploadSessionSnapshot]:
        """读取会话快照（含已上传分片）。

        Args:
            upload_id: 会话 ID。

        Returns:
            会话快照；不存在时返回 ``None``。
        """
        session = self.get_session(upload_id)
        if session is None:
            return None
        chunks = self.list_chunks(upload_id)
        uploaded_chunks = sorted(chunk.chunk_number for chunk in chunks)
        uploaded_bytes = sum(chunk.received_size for chunk in chunks)
        return UploadSessionSnapshot(
            session=session,
            uploaded_chunks=uploaded_chunks,
            uploaded_bytes=uploaded_bytes,
        )

    def list_chunks(self, upload_id: str) -> list[UploadChunkRecord]:
        """列出会话的所有已上传分片。

        Args:
            upload_id: 会话 ID。

        Returns:
            分片记录列表，按编号升序。
        """
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT upload_id, chunk_number, received_size, updated_at
                FROM upload_chunks
                WHERE upload_id = ?
                ORDER BY chunk_number ASC
                """,
                (upload_id,),
            ).fetchall()
        finally:
            connection.close()
        return [self._row_to_chunk(row) for row in rows]

    def record_chunk(self, record: UploadChunkRecord) -> None:
        """记录或更新一个已上传分片。

        使用 ``INSERT ... ON CONFLICT ... DO UPDATE`` 实现幂等：重复
        上传同一分片以最后一次写入为准。

        Args:
            record: 分片记录。
        """
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO upload_chunks (
                    upload_id, chunk_number, received_size, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT (upload_id, chunk_number) DO UPDATE SET
                    received_size = excluded.received_size,
                    updated_at = excluded.updated_at
                """,
                (
                    record.upload_id,
                    record.chunk_number,
                    record.received_size,
                    record.updated_at,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def transition_status(
        self,
        upload_id: str,
        expected_statuses: tuple[str, ...],
        new_status: str,
        updated_at: float,
    ) -> bool:
        """原子地转移会话状态。

        仅当当前状态位于 ``expected_statuses`` 中时才更新，保证
        并发调用时状态机不被破坏。

        Args:
            upload_id: 会话 ID。
            expected_statuses: 允许的当前状态集合。
            new_status: 目标状态。
            updated_at: 更新时间戳。

        Returns:
            状态被实际更新时返回 ``True``，否则返回 ``False``。
        """
        placeholders = ",".join("?" * len(expected_statuses))
        parameters = (new_status, updated_at, upload_id, *expected_statuses)
        connection = self._connect()
        try:
            cursor = connection.execute(
                f"""
                UPDATE upload_sessions
                SET status = ?, updated_at = ?
                WHERE upload_id = ? AND status IN ({placeholders})
                """,
                parameters,
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def update_checksum(
        self,
        upload_id: str,
        algorithm: Optional[str],
        value: Optional[str],
        updated_at: float,
    ) -> None:
        """更新会话的整体校验信息。

        允许在完成上传时携带新的校验参数覆盖初始化时的配置。

        Args:
            upload_id: 会话 ID。
            algorithm: 校验算法，可为 ``None``。
            value: 校验值，可为 ``None``。
            updated_at: 更新时间戳。
        """
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE upload_sessions
                SET checksum_algorithm = ?, checksum_value = ?, updated_at = ?
                WHERE upload_id = ?
                """,
                (algorithm, value, updated_at, upload_id),
            )
            connection.commit()
        finally:
            connection.close()

    def delete_session(self, upload_id: str) -> bool:
        """删除会话及其所有分片记录。

        分片记录通过外键级联删除。

        Args:
            upload_id: 会话 ID。

        Returns:
            实际删除时返回 ``True``，否则返回 ``False``。
        """
        connection = self._connect()
        try:
            cursor = connection.execute(
                "DELETE FROM upload_sessions WHERE upload_id = ?",
                (upload_id,),
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def count_active_sessions(self) -> int:
        """统计处于活动状态的会话数量。

        Returns:
            状态为 ``created`` / ``uploading`` / ``completing`` 的
            会话总数。
        """
        connection = self._connect()
        try:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS session_count FROM upload_sessions
                WHERE status IN ({ACTIVE_STATUS_SQL})
                """
            ).fetchone()
        finally:
            connection.close()
        return int(row["session_count"])

    def list_expired_sessions(self, now: float) -> list[UploadSession]:
        """列出已过期但仍处于活动状态的会话。

        仅返回 ``created`` 与 ``uploading`` 两种状态的会话；正在
        合并的会话不在此列，避免中断合并过程。

        Args:
            now: 当前时间戳。

        Returns:
            会话列表，按过期时间升序。
        """
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT {SESSION_COLUMNS} FROM upload_sessions
                WHERE expires_at < ?
                  AND status IN ('{STATUS_CREATED}', '{STATUS_UPLOADING}')
                ORDER BY expires_at ASC
                """,
                (now,),
            ).fetchall()
        finally:
            connection.close()
        return [self._row_to_session(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        """创建一个新的数据库连接。

        每次操作使用独立连接，避免跨线程共享；``foreign_keys`` 是
        按连接生效的配置，需在每次连接时重新开启。

        Returns:
            SQLite 连接。
        """
        connection = sqlite3.connect(
            str(self._database_path),
            timeout=30.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_schema(self) -> None:
        """初始化数据库结构。

        首次调用时切换日志模式为 WAL 并创建所有表与索引。所有语句
        使用 ``IF NOT EXISTS``，因此对已有数据库为幂等。
        """
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL").fetchone()
            connection.execute("PRAGMA synchronous = NORMAL")
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def _row_to_session(self, row: sqlite3.Row) -> UploadSession:
        """将数据库行转换为 :class:`UploadSession`。

        Args:
            row: 查询结果行。

        Returns:
            会话对象。
        """
        return UploadSession(
            upload_id=row["upload_id"],
            target_path=row["target_path"],
            size=int(row["size"]),
            chunk_size=int(row["chunk_size"]),
            total_chunks=int(row["total_chunks"]),
            overwrite=bool(row["overwrite"]),
            checksum_algorithm=row["checksum_algorithm"],
            checksum_value=row["checksum_value"],
            status=row["status"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            expires_at=float(row["expires_at"]),
        )

    def _row_to_chunk(self, row: sqlite3.Row) -> UploadChunkRecord:
        """将数据库行转换为 :class:`UploadChunkRecord`。

        Args:
            row: 查询结果行。

        Returns:
            分片记录。
        """
        return UploadChunkRecord(
            upload_id=row["upload_id"],
            chunk_number=int(row["chunk_number"]),
            received_size=int(row["received_size"]),
            updated_at=float(row["updated_at"]),
        )


__all__ = ["UploadSessionRepository"]
