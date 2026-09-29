# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""brew-hop: git-style dispatcher. `brew hop search …` → brew-hop-search.
Spec: docs/specs/drafts/config-layers.md § brew hop dispatch."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys

import pytest

from brew_hop_search.settings_testing import layers  # noqa: F401


def test_promote_env_both_directions():
    from brew_hop_search.hop import promote_env
    env = promote_env({"HOMEBREW_HOP_FORMAT": "json", "BREW_HOP_DB": "/x", "PATH": "/bin"})
    assert env["BREW_HOP_FORMAT"] == "json"
    assert env["HOMEBREW_HOP_DB"] == "/x"
    assert env["PATH"] == "/bin"


def test_promote_env_never_overwrites():
    from brew_hop_search.hop import promote_env
    env = promote_env({"HOMEBREW_HOP_FORMAT": "json", "BREW_HOP_FORMAT": "table"})
    assert env["BREW_HOP_FORMAT"] == "table"


def test_bare_lists_verbs_with_feature_state(layers, capsys):
    from brew_hop_search.hop import main
    assert main([]) == 0
    out = capsys.readouterr().out
    assert re.search(r"search\s", out)
    assert re.search(r"peek\s.*experimental, off", out)
    layers.set_env("BREW_HOP_FEATURES", "peek")
    main([])
    assert "experimental, on" in capsys.readouterr().out


def test_unknown_verb_exits_2_with_list(capsys):
    from brew_hop_search.hop import main
    assert main(["frobnicate"]) == 2
    err = capsys.readouterr().err
    assert "unknown verb: frobnicate" in err and "search" in err


def test_gated_verb_off_exits_2_with_hint(layers, capsys):
    from brew_hop_search.hop import main
    assert main(["peek", "user/repo"]) == 2
    assert "BREW_HOP_FEATURES=peek" in capsys.readouterr().err


def test_gated_verb_on_but_not_installed(layers, capsys, monkeypatch):
    from brew_hop_search import hop
    layers.set_env("BREW_HOP_FEATURES", "peek")
    monkeypatch.setattr(hop, "find_executable", lambda verb, d: None)
    assert hop.main(["peek", "user/repo"]) == 2
    assert "brew-hop-peek is not installed" in capsys.readouterr().err


def test_execs_sibling_binary_with_argv_and_promoted_env(tmp_path):
    """End to end: a fake brew-hop-search on PATH receives argv intact and the twin env."""
    fake = tmp_path / "brew-hop-search"
    fake.write_text("#!/bin/sh\nfor a in \"$@\"; do printf 'argv:%s\\n' \"$a\"; done\n"
                    "printf 'fmt:%s\\n' \"$BREW_HOP_FORMAT\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BREW_HOP", "HOMEBREW_HOP"))}
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["HOMEBREW_HOP_FORMAT"] = "json"
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.hop", "search", "foo", "--bar"],
                       capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "argv:foo\nargv:--bar\n" in r.stdout      # argv passed through, in order
    assert "fmt:json" in r.stdout                     # HOMEBREW_HOP_FORMAT promoted to BREW_HOP_FORMAT


def test_in_process_fallback_when_no_binary(monkeypatch, capsys):
    from brew_hop_search import hop
    monkeypatch.setattr(hop, "find_executable", lambda verb, d: None)
    called = {}
    monkeypatch.setattr(hop, "_import_entry",
                        lambda entry: (lambda argv: (called.__setitem__("argv", argv), 0)[1]))
    assert hop.main(["search", "python"]) == 0
    assert called["argv"] == ["python"]


def test_help_forms_list_verbs(capsys):
    from brew_hop_search.hop import main
    for form in (["--help"], ["-h"], ["help"]):
        assert main(form) == 0
        assert "search" in capsys.readouterr().out


def test_project_scripts_declare_brew_hop():
    import tomllib
    from pathlib import Path
    data = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["brew-hop"] == "brew_hop_search.hop:main"
