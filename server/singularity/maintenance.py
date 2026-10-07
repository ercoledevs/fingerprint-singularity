"""Offline backup/restore. Run with the API stopped; never exposes an HTTP endpoint."""
import argparse
import hashlib
import sys
import tempfile
from bson import json_util
from .security import settings, now
from .store import Store


def backup(store, output):
    header = dict(format="singularity-backup/v1", stateId=store.state_id,
                  secretFingerprint=hashlib.sha256(store.config["secret"].encode()).hexdigest(), createdAt=now())
    output.write(json_util.dumps(header) + "\n")
    for name in ("projects", "events"):
        for document in store.db[name].find({}).batch_size(100):
            output.write(json_util.dumps(dict(collection=name, document=document)) + "\n")
    output.write(json_util.dumps({"complete": True}) + "\n")


def restore(store, source):
    # Validate the complete stream before mutating the database. Spool to disk, not RAM.
    with tempfile.TemporaryFile(mode="w+") as spool:
        first = source.readline(65536)
        header = json_util.loads(first)
        if header.get("format") != "singularity-backup/v1" or header.get("stateId") != store.state_id:
            raise ValueError("Backup format or independent deletion-ledger state does not match")
        if header["secretFingerprint"] == hashlib.sha256(store.config["secret"].encode()).hexdigest():
            raise ValueError("Rotate application credentials before restoring")
        complete = False
        while True:
            line = source.readline(2_000_000)
            if not line:
                break
            item = json_util.loads(line)
            if complete:
                raise ValueError("Trailing backup data")
            if item == {"complete": True}:
                complete = True
                continue
            if set(item) != {"collection", "document"} or item["collection"] not in ("projects", "events") or not isinstance(item["document"], dict):
                raise ValueError("Invalid backup record")
            spool.write(line)
        if not complete:
            raise ValueError("Incomplete backup")
        with store.quarantine.open("w") as marker:
            marker.write("Restore in progress. API must remain offline.\n")
            marker.flush()
            import os
            os.fsync(marker.fileno())
        store.ready = False
        for name in ("sessions", "events", "projects"):
            store.db[name].delete_many({})
        spool.seek(0)
        for line in spool:
            item = json_util.loads(line)
            store.db[item["collection"]].insert_one(item["document"])
        # Old possession tokens and admin sessions must not survive restoration.
        store.events.update_many({}, {"$unset": {"tokenHash": ""}})
        store.replay()
        store.quarantine.unlink()
        store.ready = True


def main():
    parser = argparse.ArgumentParser(description="Offline Singularity backup and restore")
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--replace", action="store_true", help="Explicitly replace current database contents")
    args = parser.parse_args()
    if args.operation == "restore" and not args.replace:
        parser.error("Restore requires --replace and stopped API traffic")
    cfg = settings()
    cfg["maintenance"] = True
    store = Store(cfg)
    try:
        if args.operation == "backup":
            backup(store, sys.stdout)
        else:
            restore(store, sys.stdin)
    finally:
        store.close()


if __name__ == "__main__":
    main()
