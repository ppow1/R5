"""
R5 Data Ledger - Dumb append-only ledger, not god object
Replaces db.py 113KB god object that imported everything
Only 2 methods: append_event, read_events
Business logic lives in registries/*.json, not here
"""
import json, os, pathlib, datetime

# Config via env var, not hardcoded - central theme
DSN_ENV = "R3A_TELEMETRY_DATABASE_DSN"
DSN_DEFAULT = "postgresql://riverview:riverview@localhost:5432/riverview"

class Ledger:
    """Dumb ledger - append only, no business logic"""
    def __init__(self, dsn=None):
        self.dsn = dsn or os.getenv(DSN_ENV, DSN_DEFAULT)
        self.memory_fallback = []  # if no DB, keep in memory for lean testing

    def append_event(self, event: dict) -> dict:
        """INSERT INTO event_ledger - never mutates, only appends"""
        event = {
            "event_id": event.get("event_id", f"evt_{datetime.datetime.now().isoformat()}"),
            "timestamp": datetime.datetime.now().isoformat(),
            "actor": event.get("actor", "system"),
            "schema_version": event.get("schema_version", "1.0"),
            "payload": event
        }
        # Try PostgreSQL, fallback to memory for lean install without DB
        try:
            # import psycopg only when needed, not at top level - avoids hard dep
            import psycopg
            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO event_ledger (event_id, actor, schema_version, payload) VALUES (%s, %s, %s, %s)",
                        (event["event_id"], event["actor"], event["schema_version"], json.dumps(event["payload"]))
                    )
                conn.commit()
        except Exception as e:
            # Lean fallback - no DB required for tomorrow install
            self.memory_fallback.append(event)
        return event

    def read_events(self, since: str = None) -> list:
        """SELECT * FROM event_ledger WHERE persisted_at > since"""
        try:
            import psycopg
            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    if since:
                        cur.execute("SELECT * FROM event_ledger WHERE persisted_at > %s ORDER BY persisted_at", (since,))
                    else:
                        cur.execute("SELECT * FROM event_ledger ORDER BY persisted_at DESC LIMIT 100")
                    rows = cur.fetchall()
                    return rows
        except Exception:
            # Fallback memory
            if since:
                return [e for e in self.memory_fallback if e["timestamp"] > since]
            return self.memory_fallback[-100:]

# Singleton for convenience
ledger = Ledger()
