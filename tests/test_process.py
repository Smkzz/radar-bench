from __future__ import annotations

import sys
import time

import pytest

from radar_bench.execution.process import run_bounded


def test_bounded_process_returns_digest_and_payload() -> None:
    result = run_bounded(
        [sys.executable, "-c", "print('ok')"],
        timeout=2,
        max_output_bytes=1024,
    )
    assert result.returncode == 0
    assert result.output_bytes > 0
    assert result.output_digest.startswith("sha256:")
    assert result.payload.replace(b"\r\n", b"\n") == b"ok\n"


def test_bounded_process_stops_output_flood() -> None:
    result = run_bounded(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 1000000)"],
        timeout=2,
        max_output_bytes=1024,
    )
    assert result.output_limit_exceeded is True
    assert result.output_bytes > 1024
    assert len(result.payload) <= 1024


def test_bounded_process_stops_timeout() -> None:
    result = run_bounded(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout=0.1,
        max_output_bytes=1024,
    )
    assert result.timed_out is True
    assert result.returncode is not None


def test_bounded_process_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError):
        run_bounded([], timeout=1, max_output_bytes=1)
    with pytest.raises(ValueError):
        run_bounded([sys.executable, "-c", "pass"], timeout=0, max_output_bytes=1)
    with pytest.raises(OSError):
        run_bounded(["radar-bench-command-that-does-not-exist"], timeout=1, max_output_bytes=1)


def test_bounded_process_writes_bounded_input() -> None:
    result = run_bounded(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        timeout=2,
        max_output_bytes=1024,
        input_data=b"input",
    )
    assert result.returncode == 0
    assert result.payload.replace(b"\r\n", b"\n") == b"input"


def test_terminate_tree_posix_and_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    import radar_bench.execution.process as process_module

    class FakeProcess:
        pid = 123

    monkeypatch.setattr(process_module.os, "name", "posix")
    monkeypatch.setattr(process_module.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(process_module.os, "killpg", lambda *_args: None, raising=False)
    assert process_module._terminate_tree(FakeProcess()) is None
    def fail(*_args: object) -> None:
        raise OSError("no process")
    monkeypatch.setattr(process_module.os, "killpg", fail, raising=False)
    assert process_module._terminate_tree(FakeProcess()) == "OSError"


def test_bounded_process_keeps_diagnostics_out_of_stdout_payload() -> None:
    result = run_bounded(
        [sys.executable, "-c", "import sys; print('{}'); print('diagnostic', file=sys.stderr)"],
        timeout=2,
        max_output_bytes=1024,
    )
    assert result.payload.replace(b"\r\n", b"\n") == b"{}\n"
    assert result.stderr.replace(b"\r\n", b"\n") == b"diagnostic\n"
    assert result.output_bytes == len(result.payload) + len(result.stderr)
    assert "diagnostic" in result.excerpt


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_timeout_is_rejected_before_launch(timeout: float) -> None:
    with pytest.raises(ValueError):
        run_bounded([sys.executable, "-c", "pass"], timeout=timeout, max_output_bytes=1024)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group contract")
def test_exited_parent_cannot_leave_output_pipes_open_past_deadline() -> None:
    # The child is finite even against an unfixed runner, so a failing regression
    # does not leave an indefinite background process on the test machine.
    script = (
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(2); print(\"late-child-output\")'])"
    )
    started = time.monotonic()
    result = run_bounded([sys.executable, "-c", script], timeout=0.2, max_output_bytes=1024)
    assert result.timed_out
    assert result.cleanup_error is None
    assert b"late-child-output" not in result.payload
    assert time.monotonic() - started < 1.5
