from __future__ import annotations

from pathlib import Path

import pytest

import radar_bench.artifacts as artifacts


def test_source_url_cache_is_exact_per_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    first = "demo-1.2.3-cp311-cp311-manylinux_2_17_x86_64.whl"
    second = "demo-1.2.3-cp311-abi3-manylinux_2_17_x86_64.whl"
    metadata_calls: list[str] = []

    def metadata(url: str) -> dict[str, object]:
        metadata_calls.append(url)
        return {
            "urls": [
                {
                    "filename": first,
                    "url": f"https://files.pythonhosted.org/packages/a/{first}",
                },
                {
                    "filename": second,
                    "url": f"https://files.pythonhosted.org/packages/b/{second}",
                },
            ]
        }

    monkeypatch.setattr(artifacts, "_read_remote_json", metadata)
    cache: dict[str, str] = {}
    first_url = artifacts._source_url(first, cache)
    second_url = artifacts._source_url(second, cache)

    assert first_url.endswith("/" + first)
    assert second_url.endswith("/" + second)
    assert first_url != second_url
    assert set(cache) == {first, second}
    assert len(metadata_calls) == 2


def test_source_url_rejects_a_metadata_url_for_the_wrong_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filename = "demo-1.2.3-cp311-cp311-manylinux_2_17_x86_64.whl"
    monkeypatch.setattr(
        artifacts,
        "_read_remote_json",
        lambda _url: {
            "urls": [
                {
                    "filename": filename,
                    "url": "https://files.pythonhosted.org/packages/a/not-the-file.whl",
                }
            ]
        },
    )
    with pytest.raises(artifacts.ArtifactContractError):
        artifacts._source_url(filename, {})


def test_download_revalidates_final_redirect_url_and_filename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    filename = "demo-1.2.3-cp311-cp311-manylinux_2_17_x86_64.whl"
    expected = artifacts.ArtifactFile(filename, "sha256:" + "0" * 64, 1)

    class Response:
        headers: dict[str, str] = {}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://files.pythonhosted.org/packages/a/not-the-file.whl"

        def read(self, _size: int) -> bytes:
            return b"x"

    monkeypatch.setattr(artifacts, "urlopen", lambda *_args, **_kwargs: Response())
    destination = tmp_path / filename
    with pytest.raises(artifacts.ArtifactContractError, match="redirect"):
        artifacts._download(
            f"https://files.pythonhosted.org/packages/a/{filename}",
            destination,
            expected,
        )
    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part.whl").exists()


def test_archive_validation_rejects_traversal(tmp_path: Path) -> None:
    import zipfile

    wheel = tmp_path / "unsafe.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("../escape.py", "pass")
    errors = artifacts._validate_archive(wheel)
    assert any("unsafe archive member" in error for error in errors)


@pytest.mark.parametrize("linked_path", ["bundle", "provenance"])
def test_fetch_refuses_symlink_outputs_before_network_or_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, linked_path: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    _, bundles = artifacts._load_bundles(root, "decisive-v1.2")
    output = tmp_path / "artifacts"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "original.json"
    sentinel.write_text("keep original", encoding="utf-8")
    link = (
        output / bundles[0].artifact_id
        if linked_path == "bundle"
        else output / "provenance.json"
    )
    try:
        link.symlink_to(outside if linked_path == "bundle" else sentinel)
    except OSError:
        pytest.skip("symlink creation unavailable")
    acquired: list[str] = []

    def source(name: str, _cache: dict[str, str]) -> str:
        acquired.append(name)
        return f"https://files.pythonhosted.org/packages/{name}"

    def download(_url: str, destination: Path, _expected: artifacts.ArtifactFile) -> None:
        destination.write_bytes(b"reconstructed artifact")

    monkeypatch.setattr(artifacts, "_source_url", source)
    monkeypatch.setattr(artifacts, "_download", download)

    result = artifacts.fetch_artifacts(root, "decisive-v1.2", output)

    assert result["status"] == "BLOCKED"
    assert result["network_used"] is False
    assert not acquired
    assert list(outside.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "keep original"
    assert link.is_symlink()


def test_provenance_publication_does_not_truncate_an_external_hardlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import json
    import os

    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "artifacts"
    output.mkdir()
    sentinel = tmp_path / "original.json"
    sentinel.write_text("keep original", encoding="utf-8")
    provenance = output / "provenance.json"
    try:
        os.link(sentinel, provenance)
    except OSError:
        pytest.skip("hardlink creation unavailable")
    monkeypatch.setattr(artifacts, "_load_bundles", lambda *_args: ({}, ()))
    monkeypatch.setattr(
        artifacts,
        "verify_artifacts",
        lambda *_args: {"status": "READY", "errors": [], "catalog_digest": "fixture", "bundles": []},
    )

    result = artifacts.fetch_artifacts(root, "decisive-v1.2", output)

    assert result["status"] == "READY"
    assert sentinel.read_text(encoding="utf-8") == "keep original"
    assert json.loads(provenance.read_text(encoding="utf-8"))["suite_id"] == "decisive-v1.2"
    assert not list(output.glob(".provenance-*"))
