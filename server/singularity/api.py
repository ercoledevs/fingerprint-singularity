import asyncio
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from pymongo.errors import PyMongoError

from . import kernel, retrieval, search
from .security import mac, now, origin, settings, uid, verify_password
from .store import Store


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Identification(StrictModel):
    snapshot: dict
    requestId: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")]
    remember: StrictBool = False
    token: Annotated[str | None, Field(max_length=150)] = None


class Login(StrictModel):
    username: Annotated[str, Field(min_length=1, max_length=80)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class Project(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    origins: Annotated[list[StrictStr], Field(min_length=1, max_length=8)]
    retentionDays: Annotated[int, Field(ge=1, le=90)] = 30
    enrollment: StrictBool = True


class Limits:
    """ASGI body/admission limits apply before parsing, including chunked requests."""
    def __init__(self, app):
        self.app = app
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        original_send = send
        headers = dict(scope.get('headers', []))
        state = getattr(scope.get('app'), 'state', None)
        store = getattr(state, 'store', None)
        path = scope.get('path', '')
        key = path.rsplit('/', 1)[-1]
        supplied_origin = headers.get(b'origin', b'').decode('latin-1')
        allowed = store and path.startswith('/api/v1/identify/') and supplied_origin in store.origins.get(key, ())
        async def cors_send(message):
            if allowed and message['type'] == 'http.response.start':
                values = [(k, v) for k, v in message.get('headers', []) if k.lower() not in (b'access-control-allow-origin', b'vary')]
                message = {**message, 'headers': values + [(b'access-control-allow-origin', supplied_origin.encode('latin-1')), (b'vary', b'Origin')]}
            await original_send(message)
        send = cors_send
        if self.active >= 32:
            return await JSONResponse({"detail": "Server busy"}, 503, headers={"Retry-After": "1"})(scope, receive, send)
        self.active += 1
        try:
            data = bytearray()
            deadline = time.monotonic() + 10
            while True:
                message = await asyncio.wait_for(receive(), timeout=max(0, deadline - time.monotonic()))
                if message["type"] == "http.disconnect":
                    return
                data.extend(message.get("body", b""))
                if len(data) > 8192:
                    return await JSONResponse({"detail": "Body exceeds 8192 bytes"}, 413)(scope, receive, send)
                if not message.get("more_body"):
                    break
            sent = False
            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(data), "more_body": False}
                return await receive()
            await self.app(scope, replay, send)
        except asyncio.TimeoutError:
            await JSONResponse({"detail": "Request timeout"}, 408)(scope, receive, send)
        finally:
            self.active -= 1


@asynccontextmanager
async def lifespan(app):
    app.state.config = settings()
    app.state.store = Store(app.state.config)
    app.state.rates = {}
    app.state.rate_lock = threading.Lock()
    yield
    app.state.store.close()


app = FastAPI(title="Singularity API", version="0.3.1", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(PyMongoError)
def database_error(request, exc):
    return JSONResponse({"detail": "Database unavailable; retry shortly"}, 503, headers={"Retry-After": "2"})


@app.exception_handler(kernel.Invalid)
def invalid_snapshot(request, exc):
    return JSONResponse({"detail": exc.code}, 422)


@app.middleware("http")
async def headers(request, call_next):
    store = getattr(request.app.state, "store", None)
    if store and not store.ready:
        return JSONResponse({"detail": "Recovery required; restart the API"}, 503)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def context(request):
    return request.app.state.store, request.app.state.config


def rate(request, key, maximum):
    state = request.app.state
    with state.rate_lock:
        # Only bounded project IDs and a single login bucket are admitted as keys.
        q = state.rates.setdefault(key, deque())
        t = time.monotonic()
        while q and q[0] <= t - 60:
            q.popleft()
        if len(q) >= maximum:
            raise HTTPException(429, "Rate limit reached; retry in a minute", headers={"Retry-After": "60"})
        q.append(t)


def check_origin(request, allowed):
    value = request.headers.get("origin")
    if value not in allowed:
        raise HTTPException(403, "Origin is not allowed for this project")
    return {"Access-Control-Allow-Origin": value, "Vary": "Origin"}


def public_project(request, key):
    store, _ = context(request)
    p = store.projects.find_one({"publicKey": key}, max_time_ms=1000)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def admin(request: Request):
    store, config = context(request)
    raw = request.cookies.get("sg_admin", "")
    if not 32 <= len(raw) <= 128:
        raise HTTPException(401, "Sign in to continue")
    session = store.sessions.find_one({"_id": mac(config["secret"], raw), "expiresAt": {"$gt": now()}}, max_time_ms=1000)
    if not session:
        raise HTTPException(401, "Session expired; sign in again")
    if request.method not in ("GET", "HEAD"):
        if request.headers.get("origin") not in (None, config["origin"]):
            raise HTTPException(403, "Invalid origin")
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), mac(config["secret"], "csrf:" + raw)):
            raise HTTPException(403, "Invalid CSRF token")
    return raw


def project_by_id(store, project):
    p = store.projects.find_one({"_id": project}, max_time_ms=1000)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


def visible_event(e):
    return {k: e[k] for k in ("_id", "project", "createdAt", "expiresAt", "digest", "visitorId", "method", "reason", "snapshot", "decision")}


@app.get("/api/health")
def health(request: Request):
    store, _ = context(request)
    store.db.command("ping")
    return {"status": "ready", "version": "0.3.1"}


@app.get("/api/config")
def config(request: Request):
    store, cfg = context(request)
    p = project_by_id(store, "demo")
    return {"publicKey": p["publicKey"], "origin": cfg["origin"], "retentionDays": p["retentionDays"]}


@app.options("/api/v1/identify/{key}")
def preflight(key: str, request: Request):
    p = public_project(request, key)
    cors = check_origin(request, p["origins"])
    return Response(status_code=204, headers={**cors, "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type"})


@app.post("/api/v1/identify/{key}")
def identify(key: str, data: Identification, request: Request):
    store, cfg = context(request)
    with store.serial():
        p = public_project(request, key)
        cors = check_origin(request, p["origins"])
        rate(request, p["_id"], 120)
        s = kernel.validate(data.snapshot)
        if s["scope"] != key:
            raise HTTPException(422, "Snapshot scope must equal the project public key")
        t = now()
        bound = None
        if data.token:
            if not p["enrollment"]:
                raise HTTPException(410, "Remembered-browser enrollment is disabled")
            bound = store.events.find_one({"project": p["_id"], "anchor": True, "tokenHash": mac(cfg["secret"], data.token), "expiresAt": {"$gt": t}}, max_time_ms=1000)
            if bound is None:
                raise HTTPException(410, "Remembered-browser token expired or revoked; forget it before enrolling again")
        req_hash = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        previous = store.events.find_one({"project": p["_id"], "requestKey": data.requestId}, max_time_ms=1000)
        if previous:
            if previous["expiresAt"] <= t:
                raise HTTPException(410, "Request has expired; use a new request ID")
            if previous["requestHash"] != req_hash:
                raise HTTPException(409, "Request ID was already used for different input")
            response = dict(previous["response"])
            response["expiresAt"] = previous["expiresAt"]
            if previous["method"] == "enrolled":
                if not previous.get("tokenHash") or not p["enrollment"]:
                    raise HTTPException(410, "Enrollment has been revoked")
                response["token"] = previous["visitorId"] + "." + mac(cfg["secret"], p["_id"] + ":" + previous["visitorId"])
                if mac(cfg["secret"], response["token"]) != previous["tokenHash"]:
                    raise HTTPException(410, "Enrollment has expired")
            return JSONResponse(jsonable_encoder(response), headers=cors)
        if store.events.count_documents({"project": p["_id"], "createdAt": {"$gte": t - timedelta(days=1)}}, limit=10000, maxTimeMS=1500) >= 10000:
            raise HTTPException(429, "Daily project quota reached")
        visitor = token = None
        anchor = False
        decision = {"policy": kernel.policy(s), "status": "abstain", "candidateCount": 0, "omissions": []}
        method, reason = "unassigned", "insufficient-detail" if s['schema'] == 'singularity/v2' else "insufficient-observation"
        expires = t + timedelta(days=p["retentionDays"])
        if data.token:
            visitor, method, reason = bound["visitorId"], "remembered", "possession-token"
            expires = min(expires, bound["expiresAt"])
        elif kernel.sufficient(s):
            candidate_filter = retrieval.anchor_filter(p['_id'], s, t)
            cursor = store.events.find(candidate_filter, {"visitorId": 1, "snapshot": 1, "expiresAt": 1})
            if s['schema'] == 'singularity/v2':
                cursor = cursor.hint(retrieval.index_for(s))
            candidates = list(cursor.limit(257).max_time_ms(1500))
            decision["candidateCount"] = len(candidates)
            if data.remember:
                if not p["enrollment"]:
                    raise HTTPException(403, "Enrollment disabled for this project")
                if store.events.count_documents({"project": p["_id"], "anchor": True, "expiresAt": {"$gt": t}}, limit=512, maxTimeMS=1500) >= 512:
                    raise HTTPException(429, "Active enrollment quota reached")
                visitor, anchor, method, reason = uid("vis_"), True, "enrolled", "explicit-enrollment"
                token = visitor + "." + mac(cfg["secret"], p["_id"] + ":" + visitor)
            elif len(candidates) > 256:
                reason = "candidate-overflow"
            else:
                result = kernel.match(s, [{"id": c["visitorId"], "snapshot": c["snapshot"]} for c in candidates])
                decision.update({k: result[k] for k in ("policy", "status", "omissions")})
                reason = result["reason"]
                if result["status"] == "matched":
                    visitor, method = result["candidateId"], "inferred"
                    winner = next(c for c in candidates if c["visitorId"] == visitor)
                    expires = min(expires, winner["expiresAt"])
                    decision["comparison"] = next(c for c in result["candidates"] if c["id"] == visitor)
                elif result["status"] == "unmatched":
                    visitor, anchor, method = uid("vis_"), True, "provisional"
        event = uid("evt_")
        response = dict(eventId=event, visitorId=visitor, digest=kernel.digest(s), method=method, reason=reason,
                        decision=decision, createdAt=t, expiresAt=expires)
        document = dict(_id=event, project=p["_id"], requestKey=data.requestId, requestHash=req_hash, snapshot=s,
                        anchor=anchor, response=response, **{k: v for k, v in response.items() if k != "eventId"})
        if token:
            document["tokenHash"] = mac(cfg["secret"], token)
        # Event, decision, idempotency and new anchor commit atomically in one document.
        store.events.insert_one(document)
        response = dict(response)
        if token:
            response["token"] = token
        return JSONResponse(jsonable_encoder(response), headers=cors)


@app.post("/api/admin/login")
def login(data: Login, request: Request, response: Response):
    store, cfg = context(request)
    if request.headers.get("origin") not in (None, cfg["origin"]):
        raise HTTPException(403, "Invalid origin")
    rate(request, "admin-login", 20)
    valid = verify_password(data.password, cfg["password"])
    if not valid or not hmac.compare_digest(data.username.encode(), cfg["username"].encode()):
        raise HTTPException(401, "Invalid username or password")
    raw = secrets.token_urlsafe(32)
    store.sessions.insert_one({"_id": mac(cfg["secret"], raw), "expiresAt": now() + timedelta(hours=8)})
    response.set_cookie("sg_admin", raw, max_age=28800, httponly=True, secure=cfg["origin"].startswith("https:"), samesite="strict", path="/api/admin")
    return {"csrf": mac(cfg["secret"], "csrf:" + raw), "username": cfg["username"]}


@app.get("/api/admin/session")
def session(request: Request, raw=Depends(admin)):
    _, cfg = context(request)
    return {"username": cfg["username"], "csrf": mac(cfg["secret"], "csrf:" + raw)}


@app.post("/api/admin/logout")
def logout(request: Request, response: Response, raw=Depends(admin)):
    store, cfg = context(request)
    store.sessions.delete_one({"_id": mac(cfg["secret"], raw)})
    response.delete_cookie("sg_admin", path="/api/admin")
    return {"ok": True}


@app.get("/api/admin/projects")
def projects(request: Request, _=Depends(admin)):
    store, _ = context(request)
    return list(store.projects.find({}).limit(32).max_time_ms(1500))


def project_values(data):
    values = data.model_dump()
    try:
        values["origins"] = sorted(set(origin(o) for o in data.origins))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return values


@app.post("/api/admin/projects")
def create_project(data: Project, request: Request, _=Depends(admin)):
    store, _ = context(request)
    with store.serial():
        if store.projects.count_documents({}, limit=32) >= 32:
            raise HTTPException(409, "Maximum 32 projects per instance")
        p = dict(_id=uid("prj_"), publicKey=uid("pk_"), createdAt=now(), **project_values(data))
        store.projects.insert_one(p)
        store.refresh_origins()
        return p


@app.put("/api/admin/projects/{project}")
def update_project(project: str, data: Project, request: Request, _=Depends(admin)):
    store, _ = context(request)
    with store.serial():
        p = project_by_id(store, project)
        values = project_values(data)
        if project == "demo" and store.config["origin"] not in values["origins"]:
            raise HTTPException(422, "Keep the console origin on the demo project")
        if not values["enrollment"]:
            store.events.update_many({"project": project, "anchor": True}, {"$unset": {"tokenHash": ""}})
        # A shorter retention applies to existing records; a longer one never resurrects data.
        store.events.update_many({"project": project}, [{"$set": {"expiresAt": {"$min": ["$expiresAt", {"$add": ["$createdAt", values["retentionDays"] * 86400000]}]}}}])
        store.projects.update_one({"_id": project}, {"$set": values})
        store.refresh_origins()
        return {**p, **values}


@app.get("/api/admin/projects/{project}/events")
def events(project: str, request: Request, _=Depends(admin)):
    store, cfg = context(request)
    project_by_id(store, project)
    if len(request.query_params.multi_items()) != len(set(request.query_params.keys())):
        raise HTTPException(422, "Duplicate filters are not allowed")
    try:
        q, limit, binding = search.query(project, dict(request.query_params), cfg["secret"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "Invalid filters or expired cursor; use ISO dates with timezone")
    rows = list(store.events.find(q).sort([("createdAt", -1), ("_id", -1)]).limit(limit + 1).max_time_ms(1500))
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [visible_event(e) for e in rows], "nextCursor": search.next_cursor(cfg["secret"], binding, rows[-1]) if more else None}


@app.get("/api/admin/projects/{project}/events/{event}")
def event_detail(project: str, event: str, request: Request, _=Depends(admin)):
    store, _ = context(request)
    project_by_id(store, project)
    e = store.events.find_one({"_id": event, "project": project, "expiresAt": {"$gt": now()}}, max_time_ms=1000)
    if e is None:
        raise HTTPException(404, "Event not found or expired")
    return visible_event(e)


@app.post("/api/admin/projects/{project}/visitors/{visitor}/revoke")
def revoke(project: str, visitor: str, request: Request, _=Depends(admin)):
    store, _ = context(request)
    with store.serial():
        project_by_id(store, project)
        store.events.update_one({"project": project, "visitorId": visitor, "anchor": True}, {"$unset": {"tokenHash": ""}})
    return {"ok": True}


@app.delete("/api/admin/projects/{project}/visitors/{visitor}")
def delete_visitor(project: str, visitor: str, request: Request, _=Depends(admin)):
    store, _ = context(request)
    kernel.identifier(visitor)
    with store.serial():
        project_by_id(store, project)
        store.delete(dict(kind="visitor", project=project, visitor=visitor, time=now().isoformat()))
    return {"ok": True}


@app.delete("/api/admin/projects/{project}")
def delete_project(project: str, request: Request, _=Depends(admin)):
    store, _ = context(request)
    with store.serial():
        project_by_id(store, project)
        if project == "demo":
            raise HTTPException(409, "The built-in demo project cannot be removed")
        store.delete(dict(kind="project", project=project, time=now().isoformat()))
        request.app.state.rates.pop(project, None)
    return {"ok": True}


# Outermost: admission and absolute body deadline precede all database access.
app.add_middleware(Limits)
