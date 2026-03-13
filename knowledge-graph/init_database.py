"""
Initialize the knowledge graph database from SQL files in the init folder.

The script:
- loads environment variables from .env
- connects to PostgreSQL with SSL
- discovers init SQL files by numeric prefix (001_, 002_, ...)
- executes them in order with clear progress output
- stops immediately if any SQL statement fails
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
import ssl
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
INIT_DIR = ROOT / "init"
SQL_FILE_PATTERN = re.compile(r"^(?P<prefix>\d+)_.*\.sql$")
SQL_COMMENT_PATTERN = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.MULTILINE | re.DOTALL)
SQL_DOLLAR_QUOTE_PATTERN = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def discover_sql_files() -> list[Path]:
    """Return init SQL files sorted by numeric prefix."""
    sql_files = list(INIT_DIR.glob("*.sql"))
    if not sql_files:
        raise FileNotFoundError(f"No SQL files found in {INIT_DIR}")

    ordered_files: list[tuple[int, str, Path]] = []
    for path in sql_files:
        match = SQL_FILE_PATTERN.match(path.name)
        if not match:
            raise ValueError(
                f"Init SQL files must start with a numeric prefix like 001_: {path.name}"
            )
        ordered_files.append((int(match.group("prefix")), path.name, path))

    ordered_files.sort()
    return [path for _, _, path in ordered_files]


def split_sql_statements(sql_text: str) -> list[str]:
    """Split a SQL script into executable statements.

    This keeps the implementation simple while safely handling:
    - single and double quoted strings
    - line and block comments
    - PostgreSQL dollar-quoted blocks such as DO $$ ... $$;
    """

    statements: list[str] = []
    current: list[str] = []

    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    dollar_quote_tag: str | None = None

    i = 0
    while i < len(sql_text):
        char = sql_text[i]
        next_char = sql_text[i + 1] if i + 1 < len(sql_text) else ""

        if in_line_comment:
            current.append(char)
            if char == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            current.append(char)
            if char == "*" and next_char == "/":
                current.append(next_char)
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if dollar_quote_tag:
            if sql_text.startswith(dollar_quote_tag, i):
                current.append(dollar_quote_tag)
                i += len(dollar_quote_tag)
                dollar_quote_tag = None
            else:
                current.append(char)
                i += 1
            continue

        if in_single_quote:
            current.append(char)
            if char == "'" and next_char == "'":
                current.append(next_char)
                i += 2
                continue
            if char == "'":
                in_single_quote = False
            i += 1
            continue

        if in_double_quote:
            current.append(char)
            if char == '"':
                in_double_quote = False
            i += 1
            continue

        if char == "-" and next_char == "-":
            current.append(char)
            current.append(next_char)
            in_line_comment = True
            i += 2
            continue

        if char == "/" and next_char == "*":
            current.append(char)
            current.append(next_char)
            in_block_comment = True
            i += 2
            continue

        if char == "'":
            current.append(char)
            in_single_quote = True
            i += 1
            continue

        if char == '"':
            current.append(char)
            in_double_quote = True
            i += 1
            continue

        if char == "$":
            match = SQL_DOLLAR_QUOTE_PATTERN.match(sql_text, i)
            if match:
                dollar_quote_tag = match.group(0)
                current.append(dollar_quote_tag)
                i += len(dollar_quote_tag)
                continue

        if char == ";":
            statement = "".join(current).strip()
            if statement and has_sql_content(statement):
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(char)
        i += 1

    trailing_statement = "".join(current).strip()
    if trailing_statement and has_sql_content(trailing_statement):
        statements.append(trailing_statement)

    return statements


def has_sql_content(statement: str) -> bool:
    """Return True when a split chunk still contains executable SQL."""
    return bool(SQL_COMMENT_PATTERN.sub("", statement).strip())


def connection_settings() -> dict[str, object]:
    """Build asyncpg connection settings from environment variables."""
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "user": os.getenv("PG_USER", "pgadmin"),
        "password": os.getenv("PG_PASSWORD", ""),
        "database": os.getenv("PG_DATABASE", "appdb"),
        "ssl": ssl.create_default_context(),
    }


def format_connection_target(settings: dict[str, object]) -> str:
    """Return a human-readable host/port/database string."""
    return f"{settings['host']}:{settings['port']}/{settings['database']}"


def mask_secret(secret: str) -> str:
    """Return a short masked representation of a secret for diagnostics."""
    if not secret:
        return "not set"
    if len(secret) <= 2:
        return "*" * len(secret)
    return f"{secret[0]}{'*' * (len(secret) - 2)}{secret[-1]}"


def print_connection_diagnostics(settings: dict[str, object]) -> None:
    """Print the resolved connection settings without exposing secrets."""
    password = str(settings["password"])
    print("Resolved PostgreSQL connection settings:")
    print(f"  - host: {settings['host']}")
    print(f"  - port: {settings['port']}")
    print(f"  - database: {settings['database']}")
    print(f"  - user: {settings['user']}")
    print(f"  - password: {'set' if password else 'not set'} ({mask_secret(password)})")
    print("  - ssl: enabled (default trust store)")


def explain_connection_error(error: Exception) -> str:
    """Return a concise explanation for common connection failures."""
    if isinstance(error, asyncpg.InvalidPasswordError):
        return "Password authentication failed. The server was reached, but the credentials were rejected."
    if isinstance(error, asyncpg.InvalidAuthorizationSpecificationError):
        return "Authentication failed because the database or user configuration is invalid."
    if isinstance(error, socket.gaierror):
        return "Hostname lookup failed. PG_HOST may be wrong or not resolvable from this machine."
    if isinstance(error, ConnectionRefusedError):
        return "The server refused the TCP connection. Check host, port, firewall rules, and whether PostgreSQL is listening."
    if isinstance(error, TimeoutError):
        return "The connection attempt timed out. Check network reachability, firewall rules, and SSL requirements."
    if isinstance(error, ssl.SSLError):
        return "The SSL handshake failed. Check certificate trust, SSL requirements, and server configuration."
    if isinstance(error, OSError):
        return "A network-level error occurred while opening the connection. Check connectivity and firewall rules."
    if isinstance(error, asyncpg.PostgresError):
        return "PostgreSQL returned an error during connection setup. Review the server message below."
    return "The connection failed before any SQL initialization steps started. Review the exception details below."


def format_statement_preview(statement: str, max_length: int = 160) -> str:
    """Create a short one-line preview for progress and errors."""
    compact = " ".join(statement.split())
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3] + "..."


async def run_sql_file(conn: asyncpg.Connection, sql_file: Path) -> None:
    """Execute one SQL file inside a transaction."""
    sql_text = sql_file.read_text(encoding="utf-8")
    statements = split_sql_statements(sql_text)

    if not statements:
        print(f"Skipping {sql_file.name}: no executable SQL found.")
        return

    print(f"\nRunning {sql_file.name} ({len(statements)} statement(s))")
    transaction = conn.transaction()
    await transaction.start()

    try:
        for index, statement in enumerate(statements, start=1):
            preview = format_statement_preview(statement)
            print(f"  [{index}/{len(statements)}] {preview}")
            try:
                await conn.execute(statement)
            except Exception:
                print(f"\nERROR while running {sql_file.name} statement {index}:")
                print(preview)
                raise
    except Exception:
        if conn.is_closed():
            print("The PostgreSQL server closed the connection while handling the failed statement.")
        else:
            await transaction.rollback()
        raise
    else:
        await transaction.commit()


async def main() -> None:
    load_dotenv()

    print("Loading environment from .env")
    sql_files = discover_sql_files()
    print(f"Discovered {len(sql_files)} init file(s) in {INIT_DIR.name}:")
    for path in sql_files:
        print(f"  - {path.name}")

    settings = connection_settings()
    print_connection_diagnostics(settings)

    conn: asyncpg.Connection | None = None
    connection_target = format_connection_target(settings)
    print(f"Attempting PostgreSQL connection to {connection_target}")

    try:
        conn = await asyncpg.connect(**settings)
    except Exception as exc:
        print("\nConnection failed before database initialization began.")
        print(explain_connection_error(exc))
        print(f"Connection target: {connection_target}")
        print(f"Exception: {type(exc).__name__}: {exc}")
        raise

    print("Connection established successfully.")
    print("Authentication succeeded and SQL initialization will start next.")

    try:
        for index, sql_file in enumerate(sql_files, start=1):
            print(f"\n=== Step {index}/{len(sql_files)} ===")
            await run_sql_file(conn, sql_file)
    except Exception:
        print("\nDatabase connection/authentication was successful.")
        print("Initialization failed after connecting, during SQL execution.")
        raise
    finally:
        if conn is not None:
            await conn.close()
            print("\nConnection closed.")

    print("\nDatabase initialization completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
