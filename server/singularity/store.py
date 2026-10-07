import fcntl
import json
import os
import threading
import secrets
from contextlib import contextmanager
from pathlib import Path
from pymongo import ASCENDING, DESCENDING, MongoClient
from .security import now


class Store:
    def __init__(self, config):
        self.config = config
        path = Path(config["state"])
        path.mkdir(parents=True, exist_ok=True)
        self.lockfile = open(path / "worker.lock", "a")
        # Shared Compose state volume enforces the supported single-worker topology.
        fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.ledger = path / "deletions.jsonl"
        self.quarantine = path / "restore.pending"
        if self.quarantine.exists() and not config.get("maintenance"):
            self.lockfile.close()
            raise RuntimeError("Restore incomplete; finish recovery before starting the API")
        state_id = path / "state-id"
        if not state_id.exists():
            with state_id.open("x") as stream:
                stream.write(secrets.token_hex(16))
                stream.flush()
                os.fsync(stream.fileno())
        self.state_id = state_id.read_text().strip()
        self.mutex = threading.RLock()
        self.ready = False
        self.client = MongoClient(config["mongo"], tz_aware=True, serverSelectionTimeoutMS=5000,
                                  connectTimeoutMS=5000, socketTimeoutMS=6000, maxPoolSize=32, retryWrites=False)
        self.db = self.client.get_default_database()
        self.db.command("ping")
        self.events = self.db.events
        self.projects = self.db.projects
        self.sessions = self.db.sessions
        self.events.create_index([("project", ASCENDING), ("requestKey", ASCENDING)], unique=True)
        self.events.create_index([("project", 1), ("anchor", 1), ("expiresAt", 1)])
        self.events.create_index([("project", 1), ("createdAt", -1), ("_id", -1)])
        self.events.create_index([("project", 1), ("_id", 1)])
        for field in ["visitorId", "digest", "method", "reason", "snapshot.signals.platform"]:
            self.events.create_index([("project", 1), (field, 1), ("createdAt", -1), ("_id", -1)])
        self.events.create_index("expiresAt", expireAfterSeconds=0)
        self.sessions.create_index("expiresAt", expireAfterSeconds=0)
        self.projects.create_index("publicKey", unique=True)
        self.replay()
        self.projects.update_one({"_id": "demo"}, {"$setOnInsert": dict(name="Live demo", publicKey=config["demo_key"],
                                  origins=[config["origin"]], retentionDays=30, enrollment=True, createdAt=now())}, upsert=True)
        self.projects.update_one({"_id": "demo"}, {"$addToSet": {"origins": config["origin"]}})
        self.refresh_origins()
        self.ready = True

    def refresh_origins(self):
        self.origins = {p['publicKey']: tuple(p['origins']) for p in self.projects.find({}, {'publicKey': 1, 'origins': 1}).limit(32)}

    def sync_state_directory(self):
        fd = os.open(self.ledger.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @contextmanager
    def serial(self):
        # No unbounded per-project lock map or queue. Contending writes receive backpressure.
        if not self.mutex.acquire(blocking=False):
            from fastapi import HTTPException
            raise HTTPException(429, "Server is processing another write; retry shortly", headers={"Retry-After": "1"})
        try:
            if not self.ready:
                raise RuntimeError("Recovery required")
            yield
        finally:
            self.mutex.release()

    def apply_deletion(self, item):
        project = item["project"]
        if item["kind"] == "project":
            self.projects.delete_one({"_id": project})
            self.events.delete_many({"project": project})
        else:
            self.events.delete_many({"project": project, "visitorId": item["visitor"]})
            # Deletion also redacts contender references from retained decisions.
            for prefix in ("decision.omissions", "response.decision.omissions"):
                for field in ("candidateId", "runnerUpId"):
                    self.events.update_many({"project": project, prefix + "." + field: item["visitor"]},
                                            {"$set": {prefix + ".$[entry]." + field: None}},
                                            array_filters=[{"entry." + field: item["visitor"]}])

    def replay(self):
        if self.ledger.exists():
            with self.ledger.open() as stream:
                for line in stream:
                    self.apply_deletion(json.loads(line))

    def delete(self, item):
        # Ledger is on a separate volume from Mongo backups. Durability precedes removal.
        try:
            with self.ledger.open("a") as stream:
                stream.write(json.dumps(item, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.sync_state_directory()
            self.apply_deletion(item)
            if item['kind'] == 'project':
                self.refresh_origins()
        except Exception:
            self.ready = False
            raise

    def close(self):
        self.ready = False
        self.client.close()
        fcntl.flock(self.lockfile, fcntl.LOCK_UN)
        self.lockfile.close()
