import unicodedata
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url

from app.repositories.store import Store


def account_search(value, query):
    """Literal Unicode substring search, ignoring case and Vietnamese diacritics."""

    def normalize(text):
        return "".join(
            c
            for c in unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
            if not unicodedata.combining(c)
        )

    return int(normalize(query) in normalize(value))


class Database:
    def __init__(self, settings):
        path = make_url(settings.database_url).database
        if not path or path == ":memory:":
            raise ValueError("Use a file SQLite database; tests use temporary files.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            echo=False,
            hide_parameters=True,
        )

        @event.listens_for(self.engine, "connect")
        def pragmas(connection, _):
            connection.create_function("account_search", 2, account_search, deterministic=True)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={int(settings.sqlite_busy_timeout_ms)}")

    def migrate(self):
        connection = self.engine.raw_connection()
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                existing = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if existing:
                    raise RuntimeError(
                        "Unversioned existing database: explicit migration required; data was not modified."
                    )
                sql = (Path(__file__).parent / "migrations/versions/0001_initial.sql").read_text()
                # Set version in the same initial migration transaction.
                connection.executescript(sql.replace("COMMIT;", "PRAGMA user_version=1;\nCOMMIT;"))
                version = 1
            if version == 1:
                sql = (
                    Path(__file__).parent / "migrations/versions/0002_authentication.sql"
                ).read_text()
                connection.executescript(sql)
                version = 2
            if version == 2:
                sql = (
                    Path(__file__).parent / "migrations/versions/0003_class_rosters.sql"
                ).read_text()
                connection.executescript(sql)
                version = 3
            if version == 3:
                sql = (
                    Path(__file__).parent / "migrations/versions/0004_query_rewriting.sql"
                ).read_text()
                connection.executescript(sql)
                version = 4
            if version != 4:
                raise RuntimeError("Unsupported database migration version.")
        finally:
            connection.close()

    @contextmanager
    def read(self):
        with self.engine.connect() as connection:
            yield Store(connection)

    @contextmanager
    def write(self):
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield Store(connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
