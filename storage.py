from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = Path(os.environ.get("BRANDVEILIGHEID_DB", DATA_DIR / "brandveiligheid.db"))
PASSWORD_ITERATIONS = 600_000


class ManagedConnection(sqlite3.Connection):
    """Commit/rollback and always release the Windows file handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30.0, factory=ManagedConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(con, table):
        return set()
    return {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}


def _create_current_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            client TEXT,
            project_number TEXT,
            description TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS complexes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            complex_number TEXT,
            address TEXT,
            postal_code TEXT,
            city TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complex_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Concept',
            data_json TEXT NOT NULL DEFAULT '{}',
            created_by INTEGER,
            updated_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(complex_id) REFERENCES complexes(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(updated_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            finding_type TEXT NOT NULL DEFAULT 'Maatregel',
            code_group TEXT NOT NULL DEFAULT 'G',
            code_number INTEGER NOT NULL,
            discipline TEXT NOT NULL DEFAULT 'Bouwkundig',
            onderwerp TEXT,
            tekeningnummer TEXT,
            bouwlaag TEXT,
            ruimte TEXT,
            eis TEXT,
            gebrek TEXT,
            aantal TEXT,
            afmeting TEXT,
            maatregel TEXT,
            opmerking TEXT,
            richtlijn TEXT,
            photo_before TEXT,
            photo_after TEXT,
            created_by INTEGER,
            updated_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(updated_by) REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE(report_id, code_group, code_number)
        );

        CREATE INDEX IF NOT EXISTS idx_complexes_project ON complexes(project_id);
        CREATE INDEX IF NOT EXISTS idx_reports_complex ON reports(complex_id);
        CREATE INDEX IF NOT EXISTS idx_findings_report ON findings(report_id);
        """
    )


def _backup_legacy_database() -> None:
    backup = DATA_DIR / "brandveiligheid-pre-multiuser.backup.db"
    if DB_PATH.exists() and not backup.exists():
        shutil.copy2(DB_PATH, backup)


def _migrate_legacy_schema(con: sqlite3.Connection) -> None:
    legacy_columns = _columns(con, "projects")
    if "data_json" not in legacy_columns or "reports" in {
        row["name"] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }:
        return

    _backup_legacy_database()
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("ALTER TABLE projects RENAME TO legacy_reports")
    if _table_exists(con, "findings"):
        con.execute("ALTER TABLE findings RENAME TO legacy_findings")
    _create_current_schema(con)

    legacy_reports = con.execute("SELECT * FROM legacy_reports ORDER BY id").fetchall()
    for row in legacy_reports:
        data = json.loads(row["data_json"] or "{}")
        stamp_created = row["created_at"] or now_iso()
        stamp_updated = row["updated_at"] or stamp_created
        project_name = data.get("projectnaam") or row["title"] or "Gemigreerd project"
        project_cur = con.execute(
            "INSERT INTO projects(name,client,project_number,description,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (
                project_name,
                data.get("opdrachtgever", ""),
                data.get("projectnummer", ""),
                "Automatisch gemigreerd uit de eerdere rapportstructuur.",
                stamp_created,
                stamp_updated,
            ),
        )
        complex_cur = con.execute(
            """INSERT INTO complexes(project_id,name,complex_number,address,postal_code,city,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                project_cur.lastrowid,
                data.get("complexnaam") or row["title"] or "Gemigreerd complex",
                data.get("complexnummer", ""),
                data.get("projectadres", ""),
                data.get("postcode", ""),
                data.get("plaats", ""),
                stamp_created,
                stamp_updated,
            ),
        )
        con.execute(
            """INSERT INTO reports(id,complex_id,title,status,data_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                row["id"],
                complex_cur.lastrowid,
                row["title"],
                row["status"],
                row["data_json"],
                stamp_created,
                stamp_updated,
            ),
        )

    if _table_exists(con, "legacy_findings"):
        old_cols = _columns(con, "legacy_findings")
        copy_cols = [
            "id", "finding_type", "code_group", "code_number", "discipline", "onderwerp",
            "tekeningnummer", "bouwlaag", "ruimte", "eis", "gebrek", "aantal", "afmeting",
            "maatregel", "opmerking", "richtlijn", "photo_before", "photo_after", "created_at", "updated_at",
        ]
        for row in con.execute("SELECT * FROM legacy_findings ORDER BY id").fetchall():
            values = [row[col] if col in old_cols else "" for col in copy_cols]
            con.execute(
                f"INSERT INTO findings(report_id,{','.join(copy_cols)}) VALUES({','.join('?' for _ in range(len(copy_cols) + 1))})",
                [row["project_id"]] + values,
            )
        con.execute("DROP TABLE legacy_findings")
    con.execute("DROP TABLE legacy_reports")
    con.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        _migrate_legacy_schema(con)
        _create_current_schema(con)
        con.execute("PRAGMA user_version=2")


def hash_password(password: str, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_text))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(name: str, email: str, password: str) -> int:
    name = name.strip()
    email = normalize_email(email)
    if not name:
        raise ValueError("Vul uw naam in.")
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise ValueError("Vul een geldig e-mailadres in.")
    if len(password) < 10:
        raise ValueError("Gebruik een wachtwoord van minimaal 10 tekens.")
    stamp = now_iso()
    try:
        with connect() as con:
            cur = con.execute(
                "INSERT INTO users(name,email,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
                (name, email, hash_password(password), stamp, stamp),
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError("Voor dit e-mailadres bestaat al een account.") from exc


def authenticate_user(email: str, password: str) -> dict | None:
    with connect() as con:
        row = con.execute(
            "SELECT * FROM users WHERE email=? COLLATE NOCASE AND is_active=1",
            (normalize_email(email),),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return {key: row[key] for key in ("id", "name", "email", "is_active")}


def get_user(user_id: int) -> dict | None:
    with connect() as con:
        row = con.execute(
            "SELECT id,name,email,is_active FROM users WHERE id=? AND is_active=1", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    with connect() as con:
        row = con.execute("SELECT password_hash FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
        if row is None or not verify_password(current_password, row["password_hash"]):
            raise ValueError("Het huidige wachtwoord is niet correct.")
        if len(new_password) < 10:
            raise ValueError("Gebruik een nieuw wachtwoord van minimaal 10 tekens.")
        con.execute(
            "UPDATE users SET password_hash=?,updated_at=? WHERE id=?",
            (hash_password(new_password), now_iso(), user_id),
        )


def list_projects() -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """SELECT p.*, COUNT(DISTINCT c.id) AS complex_count, COUNT(DISTINCT r.id) AS report_count
               FROM projects p
               LEFT JOIN complexes c ON c.project_id=p.id
               LEFT JOIN reports r ON r.complex_id=c.id
               GROUP BY p.id ORDER BY p.updated_at DESC, p.name"""
        ).fetchall()


def create_project(name: str, client: str, project_number: str, description: str, user_id: int) -> int:
    if not name.strip():
        raise ValueError("Vul een projectnaam in.")
    stamp = now_iso()
    with connect() as con:
        cur = con.execute(
            """INSERT INTO projects(name,client,project_number,description,created_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (name.strip(), client.strip(), project_number.strip(), description.strip(), user_id, stamp, stamp),
        )
        return int(cur.lastrowid)


def load_project(project_id: int) -> dict:
    with connect() as con:
        row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise KeyError(project_id)
    return dict(row)


def update_project(project_id: int, payload: dict) -> None:
    with connect() as con:
        con.execute(
            "UPDATE projects SET name=?,client=?,project_number=?,description=?,updated_at=? WHERE id=?",
            (
                payload.get("name", "").strip() or "Naamloos project",
                payload.get("client", "").strip(),
                payload.get("project_number", "").strip(),
                payload.get("description", "").strip(),
                now_iso(),
                project_id,
            ),
        )


def list_complexes(project_id: int) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            """SELECT c.*, COUNT(r.id) AS report_count FROM complexes c
               LEFT JOIN reports r ON r.complex_id=c.id
               WHERE c.project_id=? GROUP BY c.id ORDER BY c.updated_at DESC,c.name""",
            (project_id,),
        ).fetchall()


def create_complex(project_id: int, name: str, complex_number: str, address: str, postal_code: str, city: str, user_id: int) -> int:
    if not name.strip():
        raise ValueError("Vul een complexnaam in.")
    stamp = now_iso()
    with connect() as con:
        cur = con.execute(
            """INSERT INTO complexes(project_id,name,complex_number,address,postal_code,city,created_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (project_id, name.strip(), complex_number.strip(), address.strip(), postal_code.strip(), city.strip(), user_id, stamp, stamp),
        )
        con.execute("UPDATE projects SET updated_at=? WHERE id=?", (stamp, project_id))
        return int(cur.lastrowid)


def load_complex(complex_id: int) -> dict:
    with connect() as con:
        row = con.execute("SELECT * FROM complexes WHERE id=?", (complex_id,)).fetchone()
    if row is None:
        raise KeyError(complex_id)
    return dict(row)


def update_complex(complex_id: int, payload: dict) -> None:
    with connect() as con:
        con.execute(
            """UPDATE complexes SET name=?,complex_number=?,address=?,postal_code=?,city=?,updated_at=? WHERE id=?""",
            (
                payload.get("name", "").strip() or "Naamloos complex",
                payload.get("complex_number", "").strip(),
                payload.get("address", "").strip(),
                payload.get("postal_code", "").strip(),
                payload.get("city", "").strip(),
                now_iso(),
                complex_id,
            ),
        )


def list_reports(complex_id: int) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute(
            "SELECT * FROM reports WHERE complex_id=? ORDER BY updated_at DESC,title", (complex_id,)
        ).fetchall()


def create_report(complex_id: int, title: str, user_id: int) -> int:
    title = title.strip() or "Rapportage brandveiligheid"
    data = {
        "report_date": date.today().strftime("%d-%m-%Y"),
        "version": "0.1",
        "gelijkwaardigheid": "In dit complex zijn geen gelijkwaardigheidsoplossingen van toepassing.",
    }
    stamp = now_iso()
    with connect() as con:
        cur = con.execute(
            """INSERT INTO reports(complex_id,title,status,data_json,created_by,updated_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (complex_id, title, "Concept", json.dumps(data, ensure_ascii=False), user_id, user_id, stamp, stamp),
        )
        return int(cur.lastrowid)


CONTEXT_KEYS = {
    "id", "title", "status", "complex_id", "project_id", "projectnaam", "projectnummer",
    "opdrachtgever", "complexnummer", "complexnaam", "projectadres", "postcode", "plaats",
}


def load_report(report_id: int) -> dict:
    with connect() as con:
        row = con.execute(
            """SELECT r.*,c.project_id,c.name AS complexnaam,c.complex_number AS complexnummer,
                      c.address AS projectadres,c.postal_code AS postcode,c.city AS plaats,
                      p.name AS projectnaam,p.client AS opdrachtgever,p.project_number AS projectnummer
               FROM reports r JOIN complexes c ON c.id=r.complex_id JOIN projects p ON p.id=c.project_id
               WHERE r.id=?""",
            (report_id,),
        ).fetchone()
    if row is None:
        raise KeyError(report_id)
    data = json.loads(row["data_json"] or "{}")
    for key in row.keys():
        if key != "data_json":
            data[key] = row[key]
    return data


def save_report(report_id: int, data: dict, user_id: int) -> None:
    clean = {key: value for key, value in data.items() if key not in CONTEXT_KEYS and key not in {"created_at", "updated_at", "created_by", "updated_by"}}
    with connect() as con:
        con.execute(
            "UPDATE reports SET title=?,status=?,data_json=?,updated_by=?,updated_at=? WHERE id=?",
            (
                data.get("title") or "Rapportage brandveiligheid",
                data.get("status") or "Concept",
                json.dumps(clean, ensure_ascii=False),
                user_id,
                now_iso(),
                report_id,
            ),
        )


def list_findings(report_id: int) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM findings WHERE report_id=? ORDER BY finding_type,code_group,code_number,id",
            (report_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def next_number(report_id: int, code_group: str) -> int:
    with connect() as con:
        row = con.execute(
            "SELECT COALESCE(MAX(code_number),0)+1 AS n FROM findings WHERE report_id=? AND code_group=?",
            (report_id, code_group),
        ).fetchone()
    return int(row["n"])


def insert_finding(report_id: int, payload: dict, user_id: int) -> int:
    columns = [
        "report_id", "finding_type", "code_group", "code_number", "discipline", "onderwerp",
        "tekeningnummer", "bouwlaag", "ruimte", "eis", "gebrek", "aantal", "afmeting",
        "maatregel", "opmerking", "richtlijn", "photo_before", "photo_after",
        "created_by", "updated_by", "created_at", "updated_at",
    ]
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        number = con.execute(
            "SELECT COALESCE(MAX(code_number),0)+1 FROM findings WHERE report_id=? AND code_group=?",
            (report_id, payload.get("code_group", "G")),
        ).fetchone()[0]
        payload = dict(payload)
        payload["code_number"] = int(number)
        stamp = now_iso()
        values = [report_id] + [payload.get(col, "") for col in columns[1:18]] + [user_id, user_id, stamp, stamp]
        cur = con.execute(
            f"INSERT INTO findings({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
            values,
        )
        return int(cur.lastrowid)


def update_finding(finding_id: int, payload: dict, user_id: int) -> None:
    columns = [
        "finding_type", "code_group", "code_number", "discipline", "onderwerp", "tekeningnummer",
        "bouwlaag", "ruimte", "eis", "gebrek", "aantal", "afmeting", "maatregel", "opmerking",
        "richtlijn", "photo_before", "photo_after",
    ]
    assignments = ",".join(f"{column}=?" for column in columns)
    with connect() as con:
        con.execute(
            f"UPDATE findings SET {assignments},updated_by=?,updated_at=? WHERE id=?",
            [payload.get(column, "") for column in columns] + [user_id, now_iso(), finding_id],
        )


def delete_finding(finding_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM findings WHERE id=?", (finding_id,))
