"""Render trusted report templates with an isolated headless Chromium process."""

import logging
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
from uuid import uuid4

from .exceptions import ApiError

logger = logging.getLogger(__name__)


def _browser_executable():
    configured = os.environ.get("REPORT_PDF_CHROMIUM_EXECUTABLE")
    if configured:
        return configured
    if sys.platform == "win32":
        for root in (
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("PROGRAMFILES"),
        ):
            if root:
                edge = (
                    Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
                )
                if edge.is_file():
                    return str(edge)
    for name in (
        "chromium", "chromium-browser", "google-chrome", "microsoft-edge"
    ):
        executable = shutil.which(name)
        if executable:
            return executable
    raise ApiError(
        "A Chromium browser is required for PDF export.", 503, "exportFormat"
    )


def _terminate_renderer(process):
    if sys.platform == "win32":
        taskkill = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
        subprocess.run(
            [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.communicate()


def render_chromium_pdf(html):
    executable = _browser_executable()
    runtime_root = Path(__file__).resolve().parent.parent / ".pdf-runtime"
    runtime = runtime_root / uuid4().hex
    created = False
    try:
        runtime_root.mkdir(mode=0o700, exist_ok=True)
        runtime.mkdir(mode=0o700)
        created = True
        env = os.environ.copy()
        env.update(TEMP=str(runtime), TMP=str(runtime), TMPDIR=str(runtime))
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("pdf_chromium_worker.py")),
                executable,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=sys.platform != "win32",
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                if sys.platform == "win32"
                else 0
            ),
        )
        try:
            output, _ = process.communicate(html.encode("utf-8"), timeout=60)
        except subprocess.TimeoutExpired:
            _terminate_renderer(process)
            raise
        if process.returncode or not output.startswith(b"%PDF-"):
            raise ApiError(
                "The PDF renderer failed.", 503, "exportFormat"
            )
        return output
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApiError(
            "The PDF renderer is unavailable or timed out.", 503, "exportFormat"
        ) from exc
    finally:
        if created:
            try:
                shutil.rmtree(runtime)
            except OSError:
                logger.exception("Could not remove PDF renderer runtime directory")
