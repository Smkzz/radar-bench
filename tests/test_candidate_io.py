from __future__ import annotations

import subprocess
import json
import sys
import time
from pathlib import Path

import pytest

import radar_bench.v1_2 as v12


def test_candidate_stdin_backpressure_obeys_protocol_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    protocol = v12.ExternalCandidateProtocol(
        "registry/python@sha256:" + "a" * 64,
        ["candidate"],
        working_directory=tmp_path,
        timeout_seconds=0.1,
    )
    packets = [
        v12.CandidatePacket(
            f"episode-{index}",
            {"context": {"detail": "x" * (128 * 1024)}},
            tuple(sorted(v12.CAPABILITIES)),
        )
        for index in range(len(v12.ALL_CASE_IDS))
    ]
    real_popen = subprocess.Popen

    def nonreading_process(_argv: object, **kwargs: object) -> subprocess.Popen[bytes]:
        # A real full stdin pipe reproduces backpressure without Docker, network,
        # or an indefinitely running child when testing the unfixed code.
        return real_popen(
            [sys.executable, "-c", "import time; time.sleep(1)"], **kwargs
        )

    monkeypatch.setattr(v12.subprocess, "Popen", nonreading_process)
    monkeypatch.setattr(protocol, "_actual_container_config", lambda: [])
    monkeypatch.setattr(protocol, "_cleanup_container", lambda: True)

    started = time.monotonic()
    result = protocol.run(packets)

    assert result["status"] == "BLOCKED"
    assert "CANDIDATE_TIMEOUT" in result["errors"]
    assert time.monotonic() - started < 0.75
    assert protocol._candidate_process is None


@pytest.mark.parametrize("episode_id", [[], {}])
def test_malformed_episode_id_blocks_without_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, episode_id: object
) -> None:
    protocol = v12.ExternalCandidateProtocol(
        "registry/python@sha256:" + "a" * 64,
        ["candidate"],
        working_directory=tmp_path,
        timeout_seconds=2,
    )
    packets = [
        v12.CandidatePacket(f"episode-{index}", {}, tuple(sorted(v12.CAPABILITIES)))
        for index in range(len(v12.ALL_CASE_IDS))
    ]
    real_popen = subprocess.Popen
    frame = json.dumps({"episode_id": episode_id, "message": "final_prediction"})
    script = (
        "import sys\n"
        f"for _ in range({len(packets)}): sys.stdin.readline()\n"
        f"print({frame!r})\n"
    )

    def malformed_process(_argv: object, **kwargs: object) -> subprocess.Popen[bytes]:
        return real_popen([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(v12.subprocess, "Popen", malformed_process)
    monkeypatch.setattr(protocol, "_actual_container_config", lambda: [])
    monkeypatch.setattr(protocol, "_cleanup_container", lambda: True)

    result = protocol.run(packets)

    assert result["status"] == "BLOCKED"
    assert "UNKNOWN_EPISODE_ID" in result["errors"]
    assert protocol._candidate_process is None
