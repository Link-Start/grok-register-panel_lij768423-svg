"""Cross-platform runtime paths and batch launch commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _load_beijing_timezone(loader=ZoneInfo):
    """Load Beijing time without making system tzdata a startup dependency."""
    try:
        return loader("Asia/Shanghai")
    except (ZoneInfoNotFoundError, OSError):
        return timezone(timedelta(hours=8), name="Asia/Shanghai")


# 面板 / 日志统一用北京时间（不受服务器 UTC 时区影响）
TZ_BEIJING = _load_beijing_timezone()


def now_beijing() -> datetime:
    return datetime.now(TZ_BEIJING)


def beijing_strftime(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return now_beijing().strftime(fmt)


class RuntimePlatformError(RuntimeError):
    pass


def _platform_name(value: str | None = None) -> str:
    return str(value or sys.platform).strip().lower()


def runtime_python(
    root: str | os.PathLike[str],
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    current_executable: str | os.PathLike[str] | None = None,
) -> Path:
    project_root = Path(root).resolve()
    platform = _platform_name(platform_name)
    env = os.environ if environ is None else environ
    configured = str(env.get("GROK_PYTHON_BIN", "") or "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            configured_path = project_root / configured_path
        # Keep the configured executable path itself. Resolving a venv's
        # ``bin/python`` symlink selects the base interpreter and drops the
        # virtual environment's site-packages.
        return Path(os.path.abspath(configured_path))

    project_python = (
        project_root / ".venv" / "Scripts" / "python.exe"
        if platform.startswith("win")
        else project_root / ".venv" / "bin" / "python"
    )
    if project_python.is_file():
        return project_python

    active_python = Path(
        sys.executable if current_executable is None else current_executable
    ).expanduser()
    return active_python if active_python.is_file() else project_python


def _xvfb_mode(environ: Mapping[str, str]) -> str:
    raw = str(environ.get("GROK_USE_XVFB", "auto") or "auto").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return "enabled"
    if raw in {"0", "false", "no", "off"}:
        return "disabled"
    if raw == "auto":
        return "auto"
    raise RuntimePlatformError("GROK_USE_XVFB 必须是 auto、1 或 0")


def _needs_xvfb(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    platform = _platform_name(platform_name)
    env = os.environ if environ is None else environ
    mode = _xvfb_mode(env)
    if not platform.startswith("linux"):
        if mode == "enabled":
            raise RuntimePlatformError("GROK_USE_XVFB=1 仅支持 Linux")
        return False
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    return not bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def batch_runtime_error(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> str | None:
    try:
        needs_xvfb = _needs_xvfb(platform_name=platform_name, environ=environ)
    except RuntimePlatformError as exc:
        return str(exc)
    if needs_xvfb and not which("xvfb-run"):
        return (
            "Linux 无图形会话且找不到 xvfb-run；请安装 xvfb，设置 DISPLAY，"
            "或确认可直接显示后设置 GROK_USE_XVFB=0"
        )
    return None


def batch_launch_command(
    root: str | os.PathLike[str],
    count: int,
    workers: int,
    *,
    python_path: str | os.PathLike[str] | None = None,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    project_root = Path(root).resolve()
    interpreter = Path(python_path) if python_path else runtime_python(
        project_root,
        platform_name=platform_name,
    )
    command = [
        str(interpreter),
        "-u",
        str(project_root / "run_batch_headless.py"),
        str(max(1, int(count))),
        str(max(1, int(workers))),
    ]
    error = batch_runtime_error(
        platform_name=platform_name,
        environ=environ,
        which=which,
    )
    if error:
        raise RuntimePlatformError(error)
    if not _needs_xvfb(platform_name=platform_name, environ=environ):
        return command
    xvfb = which("xvfb-run")
    if not xvfb:
        raise RuntimePlatformError("找不到 xvfb-run")
    return [xvfb, "-a", "-s", "-screen 0 1920x1080x24", *command]


def popen_group_kwargs(*, platform_name: str | None = None) -> dict:
    platform = _platform_name(platform_name)
    if platform.startswith("win"):
        return {
            "creationflags": int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
        }
    return {"start_new_session": True}


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _is_executable_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if _platform_name().startswith("win"):
        return path.suffix.lower() in {".exe", ".cmd", ".bat"} or path.suffix == ""
    return os.access(path, os.X_OK)


def _playwright_bundled_node(*, platform_name: str | None = None) -> Path | None:
    try:
        import playwright  # type: ignore
    except Exception:
        return None
    driver = Path(playwright.__file__).resolve().parent / "driver"
    name = "node.exe" if _platform_name(platform_name).startswith("win") else "node"
    candidate = driver / name
    return candidate if candidate.is_file() else None


def resolve_playwright_node(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> Path | None:
    """Return a Node binary Playwright can spawn. Never a POSIX shell wrapper on Windows."""
    env = os.environ if environ is None else environ
    platform = _platform_name(platform_name)
    configured = str(env.get("GROK_PLAYWRIGHT_NODE", "") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return path
    current = str(env.get("PLAYWRIGHT_NODEJS_PATH", "") or "").strip()
    if current:
        path = Path(current).expanduser()
        # Ignore the POSIX bash wrapper when running on Windows.
        if path.is_file() and not (
            platform.startswith("win") and path.name == "playwright-node" and path.suffix == ""
        ):
            return path
    if platform.startswith("win"):
        found = which("node.exe") or which("node")
        if found:
            return Path(found)
        bundled = _playwright_bundled_node(platform_name=platform)
        return bundled
    wrapper = _project_root() / "scripts" / "playwright-node"
    if wrapper.is_file():
        return wrapper
    found = which("node")
    if found:
        return Path(found)
    for cand in ("/usr/bin/node", "/usr/local/bin/node"):
        path = Path(cand)
        if path.is_file():
            return path
    return _playwright_bundled_node(platform_name=platform)


def apply_playwright_node_env(
    environ: dict[str, str] | None = None,
    *,
    platform_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, str]:
    """Pin Playwright's Node and the EPIPE guard. Safe to call before importing Playwright."""
    env = os.environ if environ is None else environ
    platform = _platform_name(platform_name)
    guard = _project_root() / "scripts" / "playwright-epipe-guard.js"
    node = resolve_playwright_node(
        platform_name=platform,
        environ=env,
        which=which,
    )
    if node is not None:
        env["PLAYWRIGHT_NODEJS_PATH"] = str(node)
        env.setdefault("GROK_PLAYWRIGHT_NODE", str(node))
        if platform.startswith("win") and guard.is_file():
            marker = str(guard)
            existing = str(env.get("NODE_OPTIONS") or "")
            extra = f"--require {marker}"
            if marker not in existing:
                env["NODE_OPTIONS"] = f"{existing} {extra}".strip()
    elif not platform.startswith("win"):
        wrapper = _project_root() / "scripts" / "playwright-node"
        if wrapper.is_file():
            env["PLAYWRIGHT_NODEJS_PATH"] = str(wrapper)
            env.setdefault("GROK_PLAYWRIGHT_NODE", "/usr/bin/node")
    return env
