"""Small, portable cases. No credentials or production endpoints are bundled."""
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from argos.case import ONCE, SOAK, Context, Spec
from argos.pack import Pack
from argos.runner import CaseFn


def apply_env(name: str) -> str:
    if name not in ("local", "preview", "staging"):
        raise ValueError("choose local, preview or staging")
    if name != "local" and not os.environ.get("ARGOS_BASE_URL"):
        raise ValueError("ARGOS_BASE_URL is required outside the local fixture")
    return name


def request(ctx: Context, path: str, expected_text: str = "") -> None:
    base = os.environ.get("ARGOS_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    ctx.check(parsed.scheme in ("http", "https") and bool(parsed.netloc), "use an HTTP(S) base URL")
    ctx.check(not (parsed.username or parsed.password or parsed.query or parsed.fragment),
              "base URL must not contain credentials, query parameters or a fragment")
    limit = float(os.environ.get("ARGOS_MAX_LATENCY_MS", "3000"))
    ctx.check(limit > 0, "latency budget must be positive")
    url = base + path
    ctx.step("request", "running")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            status = response.status
            body = response.read(1024 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status = error.code
        body = ""
    elapsed = (time.monotonic() - started) * 1000
    ctx.operation("HTTP response", kind="http", operation={"method": "GET", "url": url},
                  expected={"status": 200, "contains": expected_text},
                  actual={"status": status, "contains_expected_text": expected_text in body})
    ctx.metric("latency_ms", round(elapsed, 3), unit="ms")
    ctx.check(status == 200, f"expected HTTP 200, got {status}")
    ctx.check(expected_text in body, "expected preview text was not present")
    # Recording a threshold alone does not fail an Argos case. Enforce it explicitly.
    ctx.check(ctx.threshold("latency", actual=elapsed, operator="<=", target=limit, unit="ms"),
              "latency budget exceeded")
    ctx.step("request", "ok")


def health(ctx: Context) -> None:
    request(ctx, os.environ.get("ARGOS_HEALTH_PATH", "/health"))


def preview(ctx: Context) -> None:
    request(ctx, "/", os.environ.get("ARGOS_EXPECT_TEXT", "Preview before commit."))


def pack() -> Pack:
    return Pack(
        id="webdemo", title="Health and live preview checks",
        envs=("local", "preview", "staging"), apply_env=apply_env,
        load_cases=lambda: [
            CaseFn(Spec("web:health", "HTTP health and latency", "web", ("e2e",), (ONCE, SOAK)), health),
            CaseFn(Spec("web:preview", "Expected page content", "web", ("e2e",), (ONCE, SOAK)), preview),
        ],
    )
