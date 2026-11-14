from __future__ import annotations

import json
import os
import platform
import random
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _base_url() -> str:
    return os.environ.get("RESEARCH_HUB_URL", "http://127.0.0.1:8000").rstrip("/")


def _data_dir() -> Path:
    return Path(
        os.environ.get("RESEARCH_DATA_DIR", str(Path.home() / "research-data"))
    ).expanduser()


def _api(method: str, path: str, payload: dict | None = None) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{_base_url()}/api{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc


def _git_info() -> tuple[str | None, bool]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            ).strip()
        )
        return commit, dirty
    except Exception:
        return None, False


def _seed_from_env() -> int:
    for key in ("PYTHONHASHSEED", "SEED"):
        value = os.environ.get(key)
        if value and value.isdigit():
            return int(value)
    return random.randint(0, 2**31 - 1)


_sync_attempted = False


class Run:
    """A single tracked experimental run."""

    def __init__(
        self,
        experiment: str,
        params: dict[str, Any] | None = None,
        *,
        seed: int | None = None,
        name: str | None = None,
        log_path: str | None = None,
        flush_every: int = 20,
        url: str | None = None,
    ) -> None:
        self.experiment = experiment
        self.params = dict(params or {})
        if name:
            self.params.setdefault("name", name)
        self.params.setdefault("host_platform", platform.platform())
        self.params.setdefault("python", sys.version.split()[0])
        self.seed = seed if seed is not None else _seed_from_env()
        self.log_path = log_path
        self.flush_every = max(1, flush_every)
        if url:
            os.environ["RESEARCH_HUB_URL"] = url
        self.id: str | None = None
        self.status = "running"
        self._pending: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self._journal: Path | None = None
        self._offline = False
        self._extra_lines: list[dict[str, Any]] = []
        self._summary: dict[str, Any] = {}
        self._closed = False
        self._run_payload: dict[str, Any] = {}
        self._server_id: str | None = None

    # ------------------------------------------------------------------ context

    def __enter__(self) -> Run:
        global _sync_attempted
        if not _sync_attempted:
            _sync_attempted = True
            sync_pending(quiet=True)
        commit, dirty = _git_info()
        self._run_payload = {
            "experiment_id": self.experiment,
            "params": self.params,
            "command": " ".join(sys.argv),
            "git_commit": commit,
            "git_dirty": dirty,
            "seed": self.seed,
            "host": socket.gethostname(),
            "log_path": self.log_path,
        }
        try:
            result = _api("POST", "/runs", self._run_payload)
            self._server_id = result["id"]
            self.id = result["id"]
        except Exception as exc:
            print(f"[lab] API unavailable, recording offline: {exc}", file=sys.stderr)
            self._go_offline()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.status = "failed"
            self._summary.setdefault("error", f"{exc_type.__name__}: {exc}")
        try:
            self.close()
        except Exception as close_error:
            print(f"[lab] failed to finalise run: {close_error}", file=sys.stderr)
        return False

    # ------------------------------------------------------------------ public

    def log(self, step: int, **metrics: float) -> None:
        if self._closed:
            raise RuntimeError("run is already closed")
        for key, value in metrics.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            self._pending.append(
                {"key": key, "step": int(step), "value": numeric, "ts": _now()}
            )
        if len(self._pending) >= self.flush_every or (time.monotonic() - self._last_flush) > 1.2:
            self.flush()

    def summary(self, **values: Any) -> None:
        self._summary.update(values)

    def save_artifact(self, path: str | Path, kind: str = "figure") -> Path:
        source = Path(path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        if self._offline or not self._server_id:
            self._journal_event({"type": "artifact", "kind": kind, "path": str(source)})
            return source
        try:
            target = self._artifact_target(source)
            _api("POST", f"/runs/{self._server_id}/artifacts", {"kind": kind, "path": str(target)})
            return target
        except Exception as exc:
            print(f"[lab] artifact upload failed, journaling: {exc}", file=sys.stderr)
            self._ensure_journal()
            self._journal_event({"type": "artifact", "kind": kind, "path": str(source)})
            return source

    def flush(self) -> None:
        if not self._pending:
            self._last_flush = time.monotonic()
            return
        batch = self._pending
        self._pending = []
        self._last_flush = time.monotonic()
        if self._offline or not self._server_id:
            self._ensure_journal()
            for point in batch:
                self._journal_event({"type": "metric", **point})
            return
        try:
            _api("POST", f"/runs/{self._server_id}/metrics", {"metrics": batch})
        except Exception as exc:
            print(f"[lab] metric upload failed, switching to offline: {exc}", file=sys.stderr)
            self._go_offline()
            for point in batch:
                self._journal_event({"type": "metric", **point})

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        if self._offline or not self._server_id:
            self._ensure_journal()
            self._journal_event(
                {
                    "type": "finish",
                    "status": self.status,
                    "summary": self._summary,
                    "finished_at": _now(),
                }
            )
            print(f"[lab] run saved offline: {self._journal}", file=sys.stderr)
            return
        try:
            _api(
                "POST",
                f"/runs/{self._server_id}/finish",
                {"status": self.status, "summary": self._summary},
            )
        except Exception as exc:
            print(f"[lab] finish upload failed: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------ offline

    def _go_offline(self) -> None:
        self._offline = True
        self.id = self.id or f"{self.experiment}-LOCAL-{datetime.now():%H%M%S}"
        self._ensure_journal()

    def _ensure_journal(self) -> None:
        self._offline = True
        if self._journal is not None:
            return
        run_id = self.id or f"{self.experiment}-LOCAL-{datetime.now():%H%M%S}"
        self.id = run_id
        folder = _data_dir() / "experiments" / self.experiment / "runs"
        folder.mkdir(parents=True, exist_ok=True)
        self._journal = folder / f"{run_id}.jsonl"
        header = {
            "type": "run",
            "run": {
                **self._run_payload,
                "offline_id": run_id,
                "created_at": _now(),
            },
        }
        with self._journal.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(header, ensure_ascii=False) + "\n")

    def _journal_event(self, event: dict[str, Any]) -> None:
        self._ensure_journal()
        assert self._journal is not None
        with self._journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _artifact_target(self, source: Path) -> Path:
        if not self._server_id:
            return source
        target_dir = _data_dir() / "experiments" / self.experiment / "runs" / self._server_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return target


def sync_pending(quiet: bool = False) -> int:
    """Replay offline JSONL journals. Returns number of runs synchronised."""
    base = _data_dir() / "experiments"
    if not base.exists():
        return 0
    synced = 0
    for journal in sorted(base.glob("*/runs/*.jsonl")):
        if journal.name.endswith(".synced.jsonl"):
            continue
        try:
            lines = [
                json.loads(line)
                for line in journal.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not lines or lines[0].get("type") != "run":
                continue
            payload = lines[0]["run"]
            created = _api(
                "POST",
                "/runs",
                {key: value for key, value in payload.items() if key not in {"offline_id", "created_at"}},
            )
            run_id = created["id"]
            for event in lines[1:]:
                if event.get("type") == "metric":
                    _api(
                        "POST",
                        f"/runs/{run_id}/metrics",
                        {
                            "metrics": [
                                {
                                    "key": event["key"],
                                    "step": event["step"],
                                    "value": event["value"],
                                    "ts": event.get("ts"),
                                }
                            ]
                        },
                    )
                elif event.get("type") == "artifact":
                    _api(
                        "POST",
                        f"/runs/{run_id}/artifacts",
                        {"kind": event.get("kind", "figure"), "path": event["path"]},
                    )
                elif event.get("type") == "finish":
                    _api(
                        "POST",
                        f"/runs/{run_id}/finish",
                        {
                            "status": event.get("status", "done"),
                            "summary": event.get("summary", {}),
                        },
                    )
            target = journal.with_name(journal.name.replace(".jsonl", ".synced.jsonl"))
            journal.replace(target)
            synced += 1
            if not quiet:
                print(f"[lab] synced {journal.stem} -> {run_id}")
        except Exception as exc:
            if not quiet:
                print(f"[lab] could not sync {journal.name}: {exc}", file=sys.stderr)
            continue
    return synced
