# Quickstart

For a no-Docker installation → result → verification example with exact expected
JSON, start with the [README smoke test](../README.md#try-it-install-write-a-result-verify-it).
This document covers a **full scientific evaluation**, which additionally needs
Docker, matching source evidence, verified external artifacts, the evaluator
asset, and your own candidate image.

Package **1.1.1** and suite **decisive-v1.2** are separate version namespaces.
The former versions the installed distribution; the latter identifies the
benchmark and its `1.2-jsonl` candidate protocol. The v1.2 result's
`release_version: 1.1.0` identifies the immutable suite contract. See
[versions and compatibility](../README.md#versions-and-compatibility).

## 1. Prepare the matching source checkout and release assets

Use a disposable Linux/x86-64 machine or VM with a Docker engine, Python
3.11–3.13, Git, curl, and sha256sum. Do not use a credential-bearing development
workspace for third-party historical execution. The commands below reproduce
the published **v1.1.1** release, not an untagged checkout of `main`.

Use a fresh directory. Acquisition may access the network; evaluation must not.
The wheel intentionally excludes the evaluator material and the candidate-only
solvability receipt, so a wheel-only installation cannot perform the full run.

```sh
set -eu
git clone --depth 1 --branch v1.1.1 https://github.com/Smkzz/radar-bench.git radar-bench-source
cd radar-bench-source
python3 -m venv .venv
curl --fail --location --remote-name https://github.com/Smkzz/radar-bench/releases/download/v1.1.1/radar_bench-1.1.1-py3-none-any.whl
curl --fail --location --remote-name https://github.com/Smkzz/radar-bench/releases/download/v1.1.1/radar-bench-decisive-v1.2-evaluator.json
curl --fail --location --remote-name https://github.com/Smkzz/radar-bench/releases/download/v1.1.1/SHA256SUMS
curl --fail --location --remote-name https://github.com/Smkzz/radar-bench/releases/download/v1.1.1/SOURCE-PROVENANCE.json
test -s radar_bench-1.1.1-py3-none-any.whl
test -s radar-bench-decisive-v1.2-evaluator.json
test -s SOURCE-PROVENANCE.json
sha256sum --check --strict --ignore-missing SHA256SUMS
.venv/bin/python -m pip install --no-index --no-deps ./radar_bench-1.1.1-py3-none-any.whl
.venv/bin/radar-bench doctor
.venv/bin/radar-bench list-suites
```

`--ignore-missing` skips the sdist, which this wheel workflow does not download.
All three downloaded payloads must be present and report `OK`. Compare the
wheel digest with the separately recorded value in the README as well.
Checksums establish integrity of bytes, not independent trust in the publisher.

Verify the source and installed distribution against the release provenance:

```sh
.venv/bin/python - <<'PY'
import json
import subprocess
from importlib.metadata import version
from pathlib import Path

provenance = json.loads(Path("SOURCE-PROVENANCE.json").read_text(encoding="utf-8"))
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip()
assert provenance["release_tag"] == "v1.1.1"
assert provenance["package_version"] == version("radar-bench") == "1.1.1"
assert provenance["source_commit"] == commit
assert provenance["source_tree"] == tree
print("Release source and installed package match provenance")
PY
```

On Windows, use `.venv\Scripts\python.exe` and
`.venv\Scripts\radar-bench.exe`, and a trusted SHA-256 verifier such as
`Get-FileHash`. The shell examples and full execution target Linux/WSL; Windows
CLI availability alone is not historical-runtime qualification.

The evaluator asset stays on the host. It is not part of the wheel or sdist and
must never enter the candidate image, candidate workspace, or Docker mounts.

## 2. Fetch and verify artifacts

Store artifacts outside the source checkout when possible:

```sh
.venv/bin/radar-bench artifacts fetch --suite decisive-v1.2 --output-root /tmp/radar-artifacts
.venv/bin/radar-bench artifacts verify --suite decisive-v1.2 --artifact-root /tmp/radar-artifacts
```

Verification is local-only and fails closed on missing files, changed sizes or
digests, unexpected hosts, unsafe archives, redirects, and extra files. A
`READY` artifact inventory is a prerequisite, not evidence of a completed
benchmark. Acquire the required digest-pinned images during preparation too.

## 3. Validate the evaluator asset and candidate contract

Validate the candidate-visible contract and supplied host-side evaluator asset:

```sh
.venv/bin/radar-bench validate --suite decisive-v1.2 --evaluator-bundle radar-bench-decisive-v1.2-evaluator.json
```

Inspect both the overall information-sufficiency status and the supplied
`evaluator_bundle_supplied` audit. The overall status must be `PASS` and the
supplied bundle audit must have `valid: true`. Do not infer that an evaluator
bundle is valid solely from the command's exit code. Evaluation independently
checks it again and fails closed.

## 4. Invoke your candidate image

Radar does not ship an attribution agent. Supply a full digest-pinned Linux
image and an executable that speaks `1.2-jsonl`. Replace the image placeholder
below with your actual image digest; `radar-agent` is the executable **inside**
that image, not a Radar command. The protocol implementation is in
[`v1_2.py`](../src/radar_bench/v1_2.py), with message definitions in
[`schema/`](../schema/).

```sh
.venv/bin/radar-bench evaluate --suite decisive-v1.2 \
  --artifact-root /tmp/radar-artifacts \
  --candidate-image registry.example/candidate@sha256:<64-hex-digest> \
  --candidate-argv radar-agent \
  --evaluator-bundle radar-bench-decisive-v1.2-evaluator.json \
  --output result.json
```

Configure candidate-specific options in a wrapper inside the image. In
particular, appending `--protocol 1.2-jsonl` after `--candidate-argv` does **not**
forward it: Radar's argument parser rejects the unknown option. No extra
`--protocol` option is required for the evaluator; the suite selects the protocol.

The executor creates fresh opaque episode IDs, performs declared experiment
round trips, denies evaluation networking, bounds resources and output, and
checks cleanup. Candidate output cannot provide case IDs, evaluator labels,
gold, or post-cutoff evidence. Never add source or evaluator mounts to make a
blocked run pass.

## 5. Verify and interpret the result

Always validate the raw receipt after evaluation, including a blocked run:

```sh
.venv/bin/radar-bench verify-results result.json
```

For a valid completed receipt, the verifier prints:

```json
{
  "status": "COMPLETED",
  "suite_id": "decisive-v1.2",
  "valid": true
}
```

This describes the verifier's output for a completed run, **not a newly measured
score or a claim that this example investigator exists**. `COMPLETED` requires
the execution and isolation evidence. Missing artifacts, Docker, platform
support, or a reproducible runtime remain `BLOCKED`; they are not converted into
correct predictions. The README shows exact output for a runnable blocked path.

`evaluate` exits `0` for a completed execution and `4` for a blocked one;
`verify-results` exits `0` for a valid receipt (including `BLOCKED`) and `2` for an
invalid one. Receipt validity, execution completion, and scientific quality are
three different conclusions. Read [SCORING.md](SCORING.md) and
[LIMITATIONS.md](LIMITATIONS.md) before comparing investigator performance.
