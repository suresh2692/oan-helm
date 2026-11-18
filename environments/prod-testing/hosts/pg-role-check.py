#!/usr/bin/env python3
"""PostgreSQL role endpoint for HAProxy — openg2p-test (INSTALL-RUNBOOK step C).

Runs on pg-primary-01 and pg-replica-01 as user `postgres`, port 8008. HAProxy asks every server
"are you the primary?" / "are you a usable replica?" and routes by the answer, so the write port
follows the primary if the replica is ever promoted.

Same port and paths as Patroni's REST API, so Patroni can replace this file later without any
change to HAProxy:

  GET /primary   200 when this server accepts writes (not in recovery), else 503
  GET /replica   200 when this server is a standby, its WAL receiver is streaming, and replay is
                 no more than MAX_LAG_SECONDS behind (default 30), else 503
  GET /health    200 when PostgreSQL answers at all

The body is JSON: {"role": "primary"|"replica"|"unknown", "wal_receiver": ..., "lag_seconds": ...}.
Read-only: it runs one SELECT over the local socket (peer auth) and changes nothing.
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", "8008"))
MAX_LAG_SECONDS = float(os.environ.get("MAX_LAG_SECONDS", "30"))

# Lag = 0 when everything received has been replayed (an idle primary is not "lag"); otherwise the
# age of the last replayed commit.
QUERY = (
    "select pg_is_in_recovery(), "
    "coalesce((select status from pg_stat_wal_receiver limit 1), ''), "
    "case when not pg_is_in_recovery() then 0 "
    "     when pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() then 0 "
    "     else coalesce(extract(epoch from now() - pg_last_xact_replay_timestamp()), 0) end"
)

PRIMARY_PATHS = {"/primary", "/master", "/leader", "/read-write"}
HEALTH_PATHS = {"/", "/health", "/read-only"}


def state():
    out = subprocess.run(
        ["psql", "-XAtq", "-F", "|", "-d", "postgres", "-c", QUERY],
        capture_output=True, text=True, timeout=3,
    )
    if out.returncode != 0:
        return None
    in_recovery, receiver, lag = out.stdout.strip().split("|")
    return {
        "role": "replica" if in_recovery == "t" else "primary",
        "wal_receiver": receiver,
        "lag_seconds": round(float(lag), 3),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "pg-role-check"

    def _answer(self, with_body):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            s = state()
        except Exception:  # psql missing, timed out, …
            s = None
        if s is None:
            code, s = 503, {"role": "unknown"}
        elif path in PRIMARY_PATHS:
            code = 200 if s["role"] == "primary" else 503
        elif path == "/replica":
            ok = (s["role"] == "replica" and s["wal_receiver"] == "streaming"
                  and s["lag_seconds"] <= MAX_LAG_SECONDS)
            code = 200 if ok else 503
        elif path in HEALTH_PATHS:
            code = 200
        else:
            code, s = 404, {"error": "unknown path"}
        body = (json.dumps(s) + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if with_body:
            self.wfile.write(body)

    def do_GET(self):
        self._answer(True)

    def do_HEAD(self):
        self._answer(False)

    def do_OPTIONS(self):  # Patroni-style HAProxy templates check with OPTIONS
        self._answer(False)

    def log_message(self, *args):  # HAProxy checks every 2 s from each node; don't flood the journal
        pass


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
