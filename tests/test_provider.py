from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import radar_bench.providers.subprocess_provider as provider_module
from radar_bench.execution.process import BoundedCapture
from radar_bench.providers.subprocess_provider import SubprocessProvider


def test_subprocess_provider_rejects_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_module,
        "run_bounded",
        lambda *_args, **_kwargs: BoundedCapture(
            returncode=0,
            output_bytes=2,
            output_digest="sha256:" + "0" * 64,
            output_limit_exceeded=False,
            timed_out=False,
            excerpt="{}",
            payload=b"{}",
            cleanup_error="PROCESS_CLEANUP_TIMEOUT",
        ),
    )

    with pytest.raises(RuntimeError, match="cleanup failed"):
        SubprocessProvider(["provider"]).predict({"request": "value"})


def test_provider_accepts_json_with_stderr_diagnostics(tmp_path: Path) -> None:
    script = tmp_path / "provider.py"
    script.write_text(
        "import json, sys\n"
        "packet = json.load(sys.stdin)\n"
        "print('model ready', file=sys.stderr)\n"
        "print(json.dumps({'received': packet['request']}))\n",
        encoding="utf-8",
    )
    assert SubprocessProvider([sys.executable, str(script)]).predict({"request": "value"}) == {
        "received": "value"
    }


def test_stderr_alone_cannot_supply_a_provider_prediction(tmp_path: Path) -> None:
    script = tmp_path / "provider.py"
    script.write_text("import sys\nprint('{}', file=sys.stderr)\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        SubprocessProvider([sys.executable, str(script)]).predict({})
