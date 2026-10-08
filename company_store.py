"""Company-file discovery, migration, and non-secret login preferences.

Each company is opened from its own SQLite database file. The registry stores
only display metadata and the last username; passwords and recovery keys are
never written to it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any


@dataclass(frozen=True)
class CompanyFile:
    """A company database available from the login screen."""

    name: str
    path: str
    company_id: int = 1
    last_username: str = ""


def _safe_slug(value: str) -> str:
    """Return a filesystem-safe, readable company slug."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
    return (cleaned or "company")[:64].lower()


class CompanyStore:
    """Manage one-database-per-company files and login preferences."""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.companies_dir = self.data_dir / "companies"
        self.registry_path = self.data_dir / "company_registry.json"
        self.companies_dir.mkdir(parents=True, exist_ok=True)

    def list_companies(self) -> list[CompanyFile]:
        """Return valid registered company databases, plus discovered files."""
        records = self._load_registry()
        by_path: dict[str, CompanyFile] = {}
        for item in records:
            path = Path(item.path)
            if path.is_file():
                by_path[str(path.resolve())] = item

        for path in sorted(self.companies_dir.glob("*.db")):
            resolved = str(path.resolve())
            if resolved not in by_path:
                inspected = self.inspect_database(path)
                if inspected:
                    by_path[resolved] = inspected

        result = sorted(by_path.values(), key=lambda item: item.name.casefold())
        if result != records:
            self._save_registry(result)
        return result

    def register(
        self,
        path: str | os.PathLike[str],
        name: str,
        company_id: int = 1,
        last_username: str = "",
    ) -> CompanyFile:
        """Register or update a company database."""
        resolved = str(Path(path).resolve())
        record = CompanyFile(
            name=name.strip() or "Company",
            path=resolved,
            company_id=int(company_id),
            last_username=last_username.strip().lower(),
        )
        records = [
            existing
            for existing in self.list_companies()
            if str(Path(existing.path).resolve()) != resolved
        ]
        records.append(record)
        self._save_registry(sorted(records, key=lambda item: item.name.casefold()))
        return record

    def remember_username(self, path: str, username: str) -> None:
        """Remember only the last successful username for a company."""
        resolved = str(Path(path).resolve())
        updated: list[CompanyFile] = []
        for item in self.list_companies():
            if str(Path(item.path).resolve()) == resolved:
                item = CompanyFile(
                    name=item.name,
                    path=item.path,
                    company_id=item.company_id,
                    last_username=username.strip().lower(),
                )
            updated.append(item)
        self._save_registry(updated)

    def company_path(self, name: str) -> Path:
        """Return an unused standard path for a new company database."""
        slug = _safe_slug(name)
        candidate = self.companies_dir / f"{slug}.db"
        suffix = 2
        while candidate.exists():
            candidate = self.companies_dir / f"{slug}-{suffix}.db"
            suffix += 1
        return candidate

    def inspect_database(
        self, path: str | os.PathLike[str]
    ) -> CompanyFile | None:
        """Read company identity from an existing SQLite file without changing it."""
        db_path = Path(path).resolve()
        if not db_path.is_file():
            return None
        conn: sqlite3.Connection | None = None
        try:
            uri = db_path.as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, name FROM companies ORDER BY id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return CompanyFile(
                name=row["name"] or db_path.stem,
                path=str(db_path),
                company_id=int(row["id"]),
            )
        except sqlite3.Error:
            return None
        finally:
            if conn is not None:
                conn.close()

    def migrate_legacy_database(
        self, legacy_path: str | os.PathLike[str]
    ) -> list[CompanyFile]:
        """Split a consolidated legacy database into safe per-company copies.

        The source is never modified. Every destination is created through
        SQLite's backup API, pruned transactionally, and verified before it is
        registered.
        """
        source_path = Path(legacy_path).resolve()
        if not source_path.is_file():
            return self.list_companies()
        if self.list_companies():
            return self.list_companies()

        source = sqlite3.connect(str(source_path))
        source.row_factory = sqlite3.Row
        try:
            companies = source.execute(
                "SELECT id, name FROM companies ORDER BY id"
            ).fetchall()
        except sqlite3.Error:
            source.close()
            return []

        if not companies:
            source.close()
            return []

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = self.data_dir / "legacy_backups"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"vouchers_consolidated_{timestamp}.db"
        shutil.copy2(source_path, archive_path)

        created: list[CompanyFile] = []
        try:
            for company in companies:
                company_id = int(company["id"])
                company_name = company["name"] or f"Company {company_id}"
                destination = self.company_path(
                    f"{company_id}-{company_name}"
                )
                temp_path = destination.with_suffix(".migrating")
                target = sqlite3.connect(str(temp_path))
                try:
                    source.backup(target)
                    target.execute("PRAGMA foreign_keys = ON")
                    self._prune_to_company(target, company_id)
                    violations = target.execute(
                        "PRAGMA foreign_key_check"
                    ).fetchall()
                    if violations:
                        raise sqlite3.IntegrityError(
                            "Company split produced foreign-key violations."
                        )
                    target.commit()
                except Exception:
                    target.close()
                    temp_path.unlink(missing_ok=True)
                    raise
                else:
                    target.close()
                    temp_path.replace(destination)
                created.append(
                    CompanyFile(
                        name=company_name,
                        path=str(destination.resolve()),
                        company_id=company_id,
                    )
                )
        finally:
            source.close()

        self._save_registry(created)
        return sorted(created, key=lambda item: item.name.casefold())

    @staticmethod
    def _prune_to_company(conn: sqlite3.Connection, company_id: int) -> None:
        """Remove all other-company rows from a cloned database."""
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        table_names = [row[0] for row in table_rows]

        with conn:
            for table in table_names:
                columns = conn.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
                if any(column[1] == "company_id" for column in columns):
                    conn.execute(
                        f'DELETE FROM "{table}" WHERE company_id != ?',
                        (company_id,),
                    )

            conn.execute(
                "DELETE FROM companies WHERE id != ?",
                (company_id,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) "
                "VALUES ('active_company_id', ?)",
                (str(company_id),),
            )

            # Some legacy child tables did not declare ON DELETE CASCADE.
            # Remove only rows that became orphaned after other-company
            # parents were pruned, repeating until all dependency levels are
            # clean.
            for _pass in range(len(table_names) + 1):
                violations = conn.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
                if not violations:
                    break
                removed = 0
                for table, row_id, _parent, _fk_id in violations:
                    if row_id is None:
                        continue
                    cursor = conn.execute(
                        f'DELETE FROM "{table}" WHERE rowid = ?',
                        (row_id,),
                    )
                    removed += cursor.rowcount
                if removed == 0:
                    raise sqlite3.IntegrityError(
                        "Unable to remove orphaned legacy records."
                    )

        conn.execute("PRAGMA foreign_keys = ON")
    def _load_registry(self) -> list[CompanyFile]:
        if not self.registry_path.is_file():
            return []
        try:
            payload: Any = json.loads(
                self.registry_path.read_text(encoding="utf-8")
            )
            if not isinstance(payload, list):
                return []
            records = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                records.append(
                    CompanyFile(
                        name=str(item.get("name") or "Company"),
                        path=str(item.get("path") or ""),
                        company_id=int(item.get("company_id") or 1),
                        last_username=str(item.get("last_username") or ""),
                    )
                )
            return records
        except (OSError, ValueError, TypeError):
            return []

    def _save_registry(self, records: list[CompanyFile]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = [asdict(item) for item in records]
        fd, temp_name = tempfile.mkstemp(
            prefix="company_registry_",
            suffix=".tmp",
            dir=str(self.data_dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.registry_path)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)
