# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The README's version line at release time (scripts/readme-version.sh,
scripts/check-readme-version.sh).

Regression: v0.3.8 shipped a README whose version block read
`brew-hop-search 0.3.7 (dev+3: 206de5a+dirty)`. The block is live `-V`
output, captured before the tag exists (or not at all), and nothing
checked it. Spec: docs/meta/RELEASING.md § README version line.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str, version: str, tmp_path: Path):
    vf = tmp_path / "VERSION"
    vf.write_text(version + "\n")
    env = {**os.environ, "VERSION_FILE": str(vf),
           "BHS": f"{sys.executable} -m brew_hop_search.cli"}
    return subprocess.run([str(ROOT / "scripts" / script), *args], cwd=ROOT,
                          env=env, capture_output=True, text=True, timeout=60)


def test_release_version_line_is_exact(tmp_path):
    r = _run("readme-version.sh", version="0.3.9", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "brew-hop-search 0.3.9\n"


def test_dev_version_line_is_live(tmp_path):
    r = _run("readme-version.sh", version="0.4.0-dev", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("brew-hop-search ")


def _readme(tmp_path: Path, line: str) -> Path:
    p = tmp_path / "README.md"
    p.write_text(f"# x\n\n## Version\n\n```\n{line}\n```\n\n## License\n")
    return p


def test_check_passes_when_readme_matches(tmp_path):
    readme = _readme(tmp_path, "brew-hop-search 0.3.9")
    r = _run("check-readme-version.sh", str(readme), version="0.3.9", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr


def test_check_fails_on_the_0_3_8_regression(tmp_path):
    readme = _readme(tmp_path, "brew-hop-search 0.3.7 (dev+3: 206de5a+dirty)")
    r = _run("check-readme-version.sh", str(readme), version="0.3.8", tmp_path=tmp_path)
    assert r.returncode == 1
    assert "0.3.7 (dev+3: 206de5a+dirty)" in r.stderr
    assert "make readme" in r.stderr


def test_check_skips_dev_versions(tmp_path):
    readme = _readme(tmp_path, "brew-hop-search 0.3.7")
    r = _run("check-readme-version.sh", str(readme), version="0.4.0-dev", tmp_path=tmp_path)
    assert r.returncode == 0
