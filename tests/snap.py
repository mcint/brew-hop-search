"""Snapshot testing helper — Jane Street expect-test style.

Usage in tests:
    from tests.snap import snap

    def test_help(snap):
        result = subprocess.run(["brew-hop-search", "--help"], capture_output=True, text=True)
        snap.assert_match(result.stdout)

On first run (or with UPDATE_SNAPSHOTS=1), writes the snapshot file.
On subsequent runs, diffs against stored snapshot.
To update: UPDATE_SNAPSHOTS=1 pytest tests/
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

SNAP_DIR = Path(__file__).parent / "snapshots"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS", "") == "1"


class Snap:
    def __init__(self, name: str):
        self.path = SNAP_DIR / f"{name}.txt"
        self._call_count = 0

    def assert_match(self, actual: str, suffix: str = "") -> None:
        self._call_count += 1
        snap_path = self.path.with_suffix(f".{suffix}.txt") if suffix else self.path
        if self._call_count > 1 and not suffix:
            snap_path = self.path.with_suffix(f".{self._call_count}.txt")

        actual = actual.rstrip("\n") + "\n"

        if UPDATE or not snap_path.exists():
            SNAP_DIR.mkdir(parents=True, exist_ok=True)
            snap_path.write_text(actual)
            return

        expected = snap_path.read_text()
        if actual != expected:
            # Show unified diff
            import difflib
            diff = difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=f"expected ({snap_path.name})",
                tofile="actual",
            )
            diff_str = "".join(diff)
            pytest.fail(
                f"Snapshot mismatch for {snap_path.name}.\n"
                f"Run with UPDATE_SNAPSHOTS=1 to update.\n\n{diff_str}"
            )


def expect(actual: str, expected: str) -> None:
    """ppx_expect-style inline assertion: expected output literal in the test source.

    Usage:
        expect(run("--help"), '''\
    usage: brew-hop-search ...
    ...
    ''')
    """
    actual = actual.rstrip("\n") + "\n"
    if actual != expected:
        import difflib
        diff = difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile="expected (inline)",
            tofile="actual",
        )
        diff_str = "".join(diff)
        pytest.fail(f"Inline expect mismatch:\n\n{diff_str}")


@pytest.fixture
def snap(request) -> Snap:
    """Pytest fixture — snapshot name derived from test function name."""
    return Snap(request.node.name)
