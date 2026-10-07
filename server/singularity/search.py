"""Typed search filters, scoped and deadline-bounded by callers."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from .security import now, open_cursor, seal_cursor

METHODS = {"provisional", "inferred", "remembered", "enrolled", "unassigned"}
ALLOWED = {"event", "visitor", "digest", "prefix", "method", "reason", "platform", "after", "before", "limit", "cursor"}


def timestamp(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Use an ISO timestamp with timezone")
    return t.astimezone(timezone.utc)


def query(project, params, secret):
    if set(params) - ALLOWED:
        raise ValueError("Unknown search filter")
    filters = {k: v for k, v in params.items() if k not in ("limit", "cursor")}
    binding = hashlib.sha256(json.dumps([project, filters], sort_keys=True).encode()).hexdigest()
    limit = int(params.get("limit", "25"))
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be 1–100")
    q = {"project": project, "expiresAt": {"$gt": now()}}
    for key, field in [("event", "_id"), ("visitor", "visitorId"), ("digest", "digest"), ("method", "method"), ("reason", "reason"), ("platform", "snapshot.signals.platform")]:
        if key in filters:
            v = filters[key]
            if len(v) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", v):
                raise ValueError("Invalid " + key)
            if key == "method" and v not in METHODS:
                raise ValueError("Unknown method")
            q[field] = v
    if "prefix" in filters:
        v = filters["prefix"]
        if not 4 <= len(v) <= 68 or not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError("ID prefix must contain 4–68 letters, digits or underscores")
        if not v.startswith(("evt_", "vis_", "sg1_")):
            raise ValueError("ID prefix must start evt_, vis_ or sg1_")
        field = "_id" if v.startswith("evt_") else "visitorId" if v.startswith("vis_") else "digest"
        if field in q:
            raise ValueError("Do not combine exact and prefix search for the same ID")
        q[field] = {"$gte": v, "$lt": v + "\uffff"}
    bounds = {}
    if "after" in filters:
        bounds["$gte"] = timestamp(filters["after"])
    if "before" in filters:
        bounds["$lt"] = timestamp(filters["before"])
    if len(bounds) == 2 and bounds["$gte"] >= bounds["$lt"]:
        raise ValueError("after must precede before")
    clauses = [q]
    if bounds:
        clauses.append({"createdAt": bounds})
    if params.get("cursor"):
        c = open_cursor(secret, params["cursor"])
        if c["binding"] != binding or timestamp(c["until"]) <= now():
            raise ValueError("Expired cursor or changed filters")
        t = timestamp(c["time"])
        clauses.append({"$or": [{"createdAt": {"$lt": t}}, {"createdAt": t, "_id": {"$lt": c["id"]}}]})
    return {"$and": clauses}, limit, binding


def next_cursor(secret, binding, last):
    return seal_cursor(secret, dict(binding=binding, time=last["createdAt"].isoformat(), id=last["_id"],
                                   until=(now() + timedelta(minutes=15)).isoformat()))
