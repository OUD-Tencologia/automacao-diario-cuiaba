from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.infrastructure.postgres import (
    CaptureAlreadyRunningError,
    PostgreSQLAdvisoryLock,
)


class FakeScalarResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class FakeConnection:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.closed = False
        self.statements: list[str] = []

    def execute(self, statement, parameters):
        self.statements.append(str(statement))
        return FakeScalarResult(self.acquired)

    def close(self) -> None:
        self.closed = True


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnection:
        return self.connection


class PostgreSQLAdvisoryLockTest(unittest.TestCase):
    def test_lock_is_held_for_scope_then_released(self) -> None:
        connection = FakeConnection(acquired=True)

        with PostgreSQLAdvisoryLock(FakeEngine(connection), "folhapress_capture"):
            self.assertFalse(connection.closed)

        self.assertTrue(connection.closed)
        self.assertIn("pg_try_advisory_lock", connection.statements[0])
        self.assertIn("pg_advisory_unlock", connection.statements[1])

    def test_busy_lock_closes_connection_without_running_capture(self) -> None:
        connection = FakeConnection(acquired=False)

        with self.assertRaises(CaptureAlreadyRunningError):
            with PostgreSQLAdvisoryLock(FakeEngine(connection), "folhapress_capture"):
                self.fail("não deve entrar com lock ocupado")

        self.assertTrue(connection.closed)
        self.assertEqual(len(connection.statements), 1)


if __name__ == "__main__":
    unittest.main()
