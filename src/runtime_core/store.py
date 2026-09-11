"""SQLite ledger, no business rules or authority issuance. Laiqh."""
from contextlib import contextmanager, closing
import json
import sqlite3

from .contract_adapter import require

SCHEMA_VERSION = 1
DDL = '''
CREATE TABLE runtime_meta (id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER NOT NULL, identity TEXT NOT NULL);
CREATE TABLE registrations (registration_id TEXT PRIMARY KEY, natural_key TEXT UNIQUE NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL, binding TEXT NOT NULL);
CREATE TABLE bindings (binding_ref TEXT PRIMARY KEY, registration_id TEXT NOT NULL REFERENCES registrations, body TEXT NOT NULL);
CREATE TABLE cases (case_id TEXT PRIMARY KEY, status TEXT NOT NULL, revision INTEGER NOT NULL, binding_ref TEXT NOT NULL REFERENCES bindings);
CREATE TABLE node_runs (node_run_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases, node_id TEXT NOT NULL, status TEXT NOT NULL, input_ref TEXT NOT NULL, output_ref TEXT, UNIQUE(case_id,node_id));
CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY, node_run_id TEXT NOT NULL UNIQUE REFERENCES node_runs, owner TEXT NOT NULL, lease_token TEXT NOT NULL, deadline TEXT NOT NULL, released INTEGER NOT NULL DEFAULT 0);
CREATE TABLE ready_nodes (node_run_id TEXT PRIMARY KEY REFERENCES node_runs, claimed INTEGER NOT NULL);
CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, reference TEXT NOT NULL, content TEXT NOT NULL);
CREATE TABLE idempotency_results (scope TEXT NOT NULL, namespace TEXT NOT NULL, operation TEXT NOT NULL, target TEXT NOT NULL, idempotency_key TEXT NOT NULL, digest TEXT NOT NULL, result TEXT NOT NULL, commit_revision INTEGER NOT NULL, PRIMARY KEY(scope,namespace,operation,target,idempotency_key));
CREATE TABLE events (sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, case_id TEXT REFERENCES cases, case_revision INTEGER, type TEXT NOT NULL, body TEXT NOT NULL);
'''


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Store:
    def __init__(self, path, identity):
        self.path, self.identity = path, identity

    def initialize(self):
        require(not self.path.exists(), 'INVALID_STATE')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript(DDL)
            db.execute('INSERT INTO runtime_meta VALUES(1,?,?)', (SCHEMA_VERSION, encode(self.identity)))
            db.commit()

    def connect(self, readonly=False):
        require(self.path.is_file(), 'STORAGE_INVALID')
        db = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=0.25)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            if not readonly:
                db.execute('PRAGMA synchronous=FULL')
            row = db.execute('SELECT schema_version,identity FROM runtime_meta WHERE id=1').fetchone()
            require(row is not None and row['schema_version'] == SCHEMA_VERSION, 'STORAGE_INVALID')
            require(json.loads(row['identity']) == self.identity, 'HOST_BINDING_MISMATCH')
            return db
        except BaseException:
            db.close()
            raise

    @contextmanager
    def write(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def one(db, table, column, value):
        # Identifiers only originate at fixed service call sites, never CLI input.
        require((table, column) in {('registrations', 'registration_id'), ('registrations', 'natural_key'),
                                   ('cases', 'case_id'), ('node_runs', 'case_id'), ('node_runs', 'node_run_id'),
                                   ('bindings', 'binding_ref'), ('attempts', 'node_run_id'), ('evidence', 'evidence_id')})
        row = db.execute(f'SELECT * FROM {table} WHERE {column}=?', (value,)).fetchone()
        return dict(row) if row is not None else None
