"""Keep the public onboarding examples tied to executable package contracts."""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path
from typing import Any

import pytest

from radar_bench import __version__
from radar_bench import cli, v1_2
from radar_bench.release import SUITE_ID

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _example(marker: str, language: str) -> str:
    text = README.read_text(encoding="utf-8")
    match = re.search(
        rf"<!-- {re.escape(marker)} -->\s*```{re.escape(language)}\n(.*?)\n```",
        text,
        re.DOTALL,
    )
    assert match is not None, f"Missing executable README example: {marker}"
    return match.group(1)


def test_package_and_suite_versions_are_explicit_and_consistent() -> None:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    card = json.loads((ROOT / "benchmark-card.json").read_text(encoding="utf-8"))
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    package = manifest["project"]["version"]
    assert package == __version__ == card["version"]
    assert re.search(rf"^version: {re.escape(package)}$", citation, re.MULTILINE)
    assert f"Package release: {package}." in readme
    assert manifest["tool"]["radar"]["current_suite"] == v1_2.V12_SUITE_ID
    assert card["suite"] == v1_2.V12_SUITE_ID
    assert f"Current suite: {v1_2.V12_SUITE_ID}." in readme
    assert manifest["tool"]["radar"]["historical_reference_suite"] == SUITE_ID
    assert card["historical_reference_suite"] == SUITE_ID
    assert f"`{v1_2.V12_RELEASE_VERSION}`" in readme
    assert "not the installed package version" in readme
    assert v1_2.V12_PROTOCOL_VERSION in readme
    assert manifest["project"]["scripts"]["radar-bench"] == "radar_bench.cli:main"


def test_badges_match_supported_python_and_licenses() -> None:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    readme = README.read_text(encoding="utf-8")
    badge_lines = "\n".join(readme.splitlines()[:8])
    assert "actions/workflows/ci.yml/badge.svg?branch=main" in badge_lines
    assert (ROOT / ".github/workflows/ci.yml").is_file()
    assert "github/v/release/Smkzz/radar-bench" in badge_lines
    assert "Apache--2.0" in badge_lines
    assert "CC%20BY%204.0" in badge_lines
    assert manifest["project"]["license"] == "Apache-2.0"
    for classifier in manifest["project"]["classifiers"]:
        match = re.fullmatch(r"Programming Language :: Python :: (3\.\d+)", classifier)
        if match:
            assert match.group(1) in badge_lines
    assert "hidden tests" in readme.lower()
    assert "multi-tenant isolation" in readme
    assert "AUTONOMOUS_ATTRIBUTION_MVP = DO_NOT_BUILD" in readme


def test_current_metadata_uses_canonical_repository_urls() -> None:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    canonical = "https://github.com/Smkzz/radar-bench"
    assert all(url.startswith(canonical) for url in manifest["project"]["urls"].values())
    # Historical evidence and release notes intentionally retain their original URLs.
    for path in ("README.md", "CITATION.cff", "SECURITY.md", "docs/QUICKSTART.md"):
        assert "github.com/Smkz-Entertainment/radar-bench" not in (
            ROOT / path
        ).read_text(encoding="utf-8")


def test_readme_diagram_preserves_evaluator_and_candidate_boundaries() -> None:
    readme = README.read_text(encoding="utf-8")
    assert "```mermaid\nflowchart TD" in readme
    assert 'gold["Evaluator-only labels and gold"] --> host' in readme
    assert 'subgraph sandbox["Bounded candidate container: network denied"]' in readme
    assert 'receipt --> verifier["verify-results: strict contract validation"]' in readme
    assert "gold --> candidate" not in readme


@pytest.mark.parametrize(
    "document", ["README.md", "docs/QUICKSTART.md", "docs/REPRODUCIBILITY.md"]
)
def test_documented_evaluation_commands_parse(document: str) -> None:
    text = (ROOT / document).read_text(encoding="utf-8").replace("\\\n", " ")
    commands = [line.strip() for line in text.splitlines() if "radar-bench evaluate " in line]
    assert commands, f"No evaluation commands checked in {document}"
    for command in commands:
        command = command.split(" || ", 1)[0]
        args = shlex.split(command)
        assert args[0].endswith("radar-bench")
        parsed = cli.build_parser().parse_args(args[1:])
        assert parsed.command == "evaluate"
        assert parsed.suite in (SUITE_ID, v1_2.V12_SUITE_ID)
        assert parsed.output == "result.json"


def test_readme_smoke_creates_and_verifies_the_documented_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RADAR_BENCH_CACHE", str(tmp_path / "cache"))

    def forbidden_candidate(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("The no-Docker README example must not start a candidate")

    monkeypatch.setattr(v1_2, "ExternalCandidateProtocol", forbidden_candidate)
    command = _example("readme-smoke-command", "sh")
    assert 'test "$status" -eq 4' in command
    lines = [line for line in command.splitlines() if line.startswith(".venv/bin/radar-bench ")]
    assert len(lines) == 2
    evaluate_args = shlex.split(lines[0].split(" || ", 1)[0])[1:]
    assert cli.main(evaluate_args) == cli.EXIT_EXTERNAL
    stdout_result = json.loads(capsys.readouterr().out)
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result == stdout_result
    expected = json.loads(_example("readme-smoke-result", "json"))
    assert {key: result[key] for key in expected} == expected
    assert "score" not in result
    verify_args = shlex.split(lines[1])[1:]
    assert cli.main(verify_args) == cli.EXIT_OK
    verification = json.loads(capsys.readouterr().out)
    assert verification == json.loads(_example("readme-smoke-verification", "json"))


def test_readme_installation_is_version_pinned_and_offline_after_download() -> None:
    readme = README.read_text(encoding="utf-8")
    assert f"releases/download/v{__version__}/radar_bench-{__version__}-py3-none-any.whl" in readme
    assert "sha256sum --check --strict" in readme
    assert "pip install --no-index --no-deps" in readme
    assert "not a wheel rebuilt" in readme
    assert "valid: true" in readme
    assert "not that the" in readme
