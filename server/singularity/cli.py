"""Modern read-only terminal client. Installable without server dependencies."""
import argparse
import getpass
import ipaddress
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class APIError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


def endpoint(value):
    u = urlsplit(value)
    if u.username or u.password or u.path not in ("", "/") or u.query or u.fragment or not u.hostname:
        raise ValueError("Use a server origin without credentials or a path")
    if u.scheme != "https":
        try:
            loopback = ipaddress.ip_address(u.hostname).is_loopback
        except ValueError:
            loopback = False
        if u.scheme != "http" or not loopback:
            raise ValueError("HTTPS is required; HTTP is allowed only for literal loopback addresses")
    _ = u.port
    return value.rstrip("/")


def private_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise ValueError("Session file must be owned by you, regular, non-symlink and mode 0600")


def check_parents(path):
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError("Session path must not contain symlinks")
    if path.parent.exists():
        info = path.parent.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("Session directory must be owned by you and mode 0700")


def save_session(path, data):
    check_parents(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() or path.is_symlink():
        private_file(path)
    fd, name = tempfile.mkstemp(prefix=".session-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_session(path):
    check_parents(path)
    if not path.exists():
        raise ValueError("No session. Run singularity login first")
    private_file(path)
    # O_NOFOLLOW closes the final-component symlink race.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        return json.load(stream)


def parser():
    p = argparse.ArgumentParser(prog="singularity", description="Singularity · self-hosted identification console")
    p.add_argument("--session-file", type=Path, default=Path.home() / ".config/singularity/session.json")
    p.add_argument("--json", action="store_true", help="Machine-readable stdout; errors use stderr")
    sub = p.add_subparsers(dest="command", required=True)
    login = sub.add_parser("login", help="Create an eight-hour local admin session")
    login.add_argument("--url", default="http://127.0.0.1:8080")
    login.add_argument("--username", default="admin")
    login.add_argument("--password-stdin", action="store_true", help="Read one line from stdin, never a command argument")
    sub.add_parser("logout", help="Revoke the server session and remove local credentials")
    sub.add_parser("projects", help="List projects and their public integration keys")
    events = sub.add_parser("events", help="Search events using combinable filters (AND)")
    events.add_argument("--project", required=True)
    for name, help_text in [
        ("event", "Exact event ID"), ("visitor", "Exact visitor ID"), ("digest", "Exact observation digest"),
        ("prefix", "ID prefix: evt_, vis_, sg1_ or sg2_ followed by characters"), ("method", "provisional/inferred/enrolled/remembered/unassigned"),
        ("reason", "Exact decision reason"), ("platform", "macos/windows/linux/ios/android/chromeos"),
        ("after", "Inclusive ISO timestamp, e.g. 2026-10-01T00:00:00Z"), ("before", "Exclusive ISO timestamp"),
        ("cursor", "Next cursor from a previous page; keep filters unchanged")]:
        events.add_argument("--" + name, help=help_text)
    events.add_argument("--limit", type=int, default=25, help="1–100 events; newest first")
    detail = sub.add_parser("show", help="Inspect an event, observations and decision")
    detail.add_argument("event")
    detail.add_argument("--project", required=True)
    evaluation = sub.add_parser("evaluate", help="Evaluate labeled JSONL observations offline, without signing in")
    evaluation.add_argument("file", type=Path)
    return p


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.is_redirect:
        raise ValueError("Redirect refused; use the final server origin")
    if response.is_error:
        try:
            detail = response.json().get("detail", "Request failed")
            if not isinstance(detail, str):
                detail = "Input rejected"
        except ValueError:
            detail = "Request failed"
        raise APIError(response.status_code, detail[:240])
    return response.json()


def display(data, command):
    console = Console(highlight=False)
    if command == "projects":
        table = Table(title="SINGULARITY  /  Projects", header_style="bold cyan", expand=True)
        for label in ["Project", "ID", "Public key", "Retention"]:
            table.add_column(label, overflow="fold")
        for p in data:
            table.add_row(*[Text(str(v)) for v in [p["name"], p["_id"], p["publicKey"], f'{p["retentionDays"]} days']])
        console.print(table)
    elif command == "events":
        table = Table(title="SINGULARITY  /  Event explorer", header_style="bold cyan", expand=True)
        for label in ["Time (UTC)", "Event ID", "Visitor ID", "Method", "Reason"]:
            table.add_column(label, overflow="fold")
        for e in data["items"]:
            table.add_row(e["createdAt"], e["_id"], e["visitorId"] or "Unassigned", e["method"], e["reason"])
        console.print(table)
        if not data["items"]:
            console.print("No events match these filters.")
        if data["nextCursor"]:
            console.print("Next page: repeat the filters and add --cursor", style="dim")
            console.print(data["nextCursor"], markup=False, soft_wrap=True)
    elif command == "show":
        console.print(Panel(f'Event: {data["_id"]}\nVisitor: {data["visitorId"] or "Unassigned"}\nMethod: {data["method"]}\nReason: {data["reason"]}\nExpires: {data["expiresAt"]}', title="Singularity / Event", border_style="cyan"), markup=False)
        console.print_json(data=data)
    elif command == "evaluate":
        table = Table(title="SINGULARITY  /  Identification evaluation", header_style="bold cyan", expand=True)
        for label in ["Cohort", "Source", "Visits / devices", "Pair coverage", "False links", "Link yield"]:
            table.add_column(label, overflow="fold")
        def percent(value):
            return "N/A" if value is None else f"{value:.2%}"
        for c in data["cohorts"]:
            m = c["singularity"]["allPairs"]
            table.add_row(Text(f'{c["project"]} / {c["configuration"]} / {c["mode"]}'), c["source"],
                          f'{c["observations"]} / {c["devices"]}', percent(m["rates"]["pairCoverage"]["value"]),
                          str(m["falseLinks"]), percent(m["rates"]["endToEndLinkYield"]["value"]))
        console.print(table)
        console.print(data["interpretation"], markup=False, style="dim")
        console.print("Use --json before evaluate for denominators, cross-browser pairs, per-device and reference results.", style="dim")
    else:
        console.print(data["message"], markup=False, style="green")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "evaluate":
            from .evaluation import run
            data = run(args.file)
        elif args.command == "login":
            base = endpoint(args.url)
            if args.password_stdin:
                password = sys.stdin.readline().rstrip("\r\n")
            elif sys.stdin.isatty():
                password = getpass.getpass("Admin password: ")
            else:
                raise ValueError("Noninteractive login requires --password-stdin")
            with httpx.Client(base_url=base, timeout=15, follow_redirects=False, trust_env=False) as client:
                result = request(client, "POST", "/api/admin/login", json=dict(username=args.username, password=password))
                save_session(args.session_file, dict(url=base, token=client.cookies.get("sg_admin"), csrf=result["csrf"]))
            data = {"message": "Signed in. Session saved privately; expires in eight hours."}
        else:
            session = load_session(args.session_file)
            base = endpoint(session["url"])
            with httpx.Client(base_url=base, timeout=15, follow_redirects=False, trust_env=False,
                              cookies={"sg_admin": session["token"]}, headers={"X-CSRF-Token": session["csrf"]}) as client:
                if args.command == "logout":
                    try:
                        request(client, "POST", "/api/admin/logout")
                    except APIError as exc:
                        if exc.status != 401:
                            raise ValueError("Local credentials removed; remote revocation could not be confirmed") from None
                    except httpx.HTTPError:
                        raise ValueError("Local credentials removed; server unreachable. Remote session expires within eight hours") from None
                    finally:
                        args.session_file.unlink()
                    data = {"message": "Session revoked and local credentials removed."}
                elif args.command == "projects":
                    data = request(client, "GET", "/api/admin/projects")
                else:
                    from urllib.parse import quote
                    path = "/api/admin/projects/" + quote(args.project, safe="") + "/events"
                    if args.command == "show":
                        data = request(client, "GET", path + "/" + quote(args.event, safe=""))
                    else:
                        filters = {k: v for k, v in vars(args).items() if k in {"event", "visitor", "digest", "prefix", "method", "reason", "platform", "after", "before", "cursor", "limit"} and v is not None}
                        data = request(client, "GET", path, params=filters)
        if args.json:
            print(json.dumps(data, ensure_ascii=False))
        else:
            display(data, args.command)
        return 0
    except (ValueError, OSError, KeyError, httpx.HTTPError) as e:
        # Network exception text can embed a URL; report only its category.
        message = type(e).__name__ if isinstance(e, httpx.HTTPError) else str(e)
        Console(stderr=True).print("Error: " + message, style="red", markup=False)
        return 1


if __name__ == "__main__":
    sys.exit(main())
