#!/usr/bin/env python3
"""Regenerate the ENVIRONMENT block in docs/brew-hop-search.1.md from settings.py.
Run: make man-env   (tests/test_settings_docs_man.py fails when the block is stale)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brew_hop_search.settings_docs import render_man_environment, MAN_BEGIN, MAN_END  # noqa: E402

doc = Path(__file__).resolve().parents[1] / "docs" / "brew-hop-search.1.md"
text = doc.read_text()
start, end = text.index(MAN_BEGIN) + len(MAN_BEGIN), text.index(MAN_END)
doc.write_text(text[:start] + "\n" + render_man_environment() + text[end:])
print(f"updated {doc}")
