"""Tests for quickrun.

quickrun refuses to import off Windows (it needs winreg), so the whole
module is skipped elsewhere. Nothing here touches the real registry or
your real PowerShell profiles - profile paths are redirected to tmp_path.
"""

import argparse
import codecs
import io
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="quickrun is Windows-only")

if sys.platform == "win32":
    import quickrun as q
else:  # pragma: no cover - the marker above skips every test
    q = None


class _Tty(io.StringIO):
    """A stdin/stdout stand-in that claims to be an interactive console."""

    def isatty(self):
        return True


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """One fake profile.ps1, for a shell that is present."""
    path = tmp_path / "profile.ps1"
    monkeypatch.setattr(q, "_profile_targets",
                        lambda: [(str(path), "powershell")])
    monkeypatch.setattr(q, "_profile_paths", lambda: [str(path)])
    return path


# ------------------------------------------------------- profile encoding

@pytest.mark.parametrize("raw, expected", [
    (b"\xef\xbb\xbfSet-Alias -Name a", "utf-8-sig"),
    ("# hi".encode("utf-16"), "utf-16"),                     # BOM, little endian
    (codecs.BOM_UTF16_BE + "# hi".encode("utf-16-be"), "utf-16"),  # BOM, big endian
    # BOM-less UTF-16, which PowerShell 5.1 can leave behind. This is the
    # shape that decodes as valid UTF-8 (every other byte is NUL).
    ("# hi".encode("utf-16-le"), "utf-16-le"),
    ("# hi".encode("utf-16-be"), "utf-16-be"),
    (b"# plain ascii profile", None),
    (b"", None),
])
def test_profile_encoding_detects_bom(raw, expected):
    assert q._profile_encoding(raw) == expected


def test_utf16_profile_is_not_corrupted(profile):
    """Regression: cp1252 decodes UTF-16 as mojibake without erroring, so
    guessing the encoding used to rewrite the profile as garbage."""
    body = "# my profile\r\nfunction hi { Write-Host hi }\r\n"
    profile.write_bytes(body.encode("utf-16"))

    q._add_cmd_alias("zzz", "C:/tools/a.exe")

    # PowerShell must still be able to read what we wrote back.
    text = profile.read_bytes().decode("utf-16")
    assert "function hi { Write-Host hi }" in text
    assert q._profile_aliases(str(profile)) == {"zzz": "C:/tools/a.exe"}


def test_utf16_profile_keeps_its_encoding(profile):
    profile.write_bytes("# mine\r\n".encode("utf-16"))
    q._add_cmd_alias("zzz", "C:/a.exe")
    assert q._profile_encoding(profile.read_bytes()) == "utf-16"


def test_add_remove_round_trip_preserves_user_content(profile):
    profile.write_text("# mine\r\nfunction hi { 'x' }\r\n", encoding="utf-8-sig")

    q._add_cmd_alias("zzz", "C:/a.exe")
    assert q._profile_aliases(str(profile)) == {"zzz": "C:/a.exe"}

    q._remove_cmd_alias("zzz")
    text, encoding = q._read_profile(str(profile))
    assert encoding == "utf-8-sig"
    assert "function hi { 'x' }" in text
    assert "zzz" not in text


def test_round_trip_is_byte_identical(profile):
    """Adding then removing an alias must leave the rest of the file alone,
    including line endings quickrun did not author."""
    body = b"# mine\r\n\n# an LF-only line\r\nfunction hi { 'x' }\r\n"
    profile.write_bytes(body)

    q._add_cmd_alias("zzz", "C:/a.exe")
    q._remove_cmd_alias("zzz")

    assert profile.read_bytes() == body


def test_alias_value_containing_a_quote_round_trips(profile):
    profile.write_text("", encoding="utf-8-sig")
    value = "C:/it's here/a.exe"
    q._add_cmd_alias("zzz", value)
    assert q._profile_aliases(str(profile)) == {"zzz": value}


def test_readding_an_alias_does_not_duplicate_the_line(profile):
    profile.write_text("", encoding="utf-8-sig")
    q._add_cmd_alias("zzz", "C:/a.exe")
    q._add_cmd_alias("zzz", "C:/b.exe")
    text, _ = q._read_profile(str(profile))
    assert text.count("Set-Alias -Name zzz") == 1
    assert q._profile_aliases(str(profile)) == {"zzz": "C:/b.exe"}


def test_no_profile_is_created_for_an_absent_shell(tmp_path, monkeypatch):
    present = tmp_path / "present.ps1"
    absent = tmp_path / "absent.ps1"
    monkeypatch.setattr(q, "_profile_targets", lambda: [
        (str(present), "powershell"),            # always on Windows
        (str(absent), "quickrun-no-such-shell"),  # never on PATH
    ])
    monkeypatch.setattr(q, "_profile_paths",
                        lambda: [str(present), str(absent)])

    written = q._add_cmd_alias("zzz", "C:/a.exe")

    assert written == [str(present)]
    assert present.is_file()
    assert not absent.exists()


# ------------------------------------------------------------ _choose_path

def test_choose_path_picks_by_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "2")
    assert q._choose_path(["a.exe", "b.exe"]) == "b.exe"


def test_choose_path_returns_none_on_cancel(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert q._choose_path(["a.exe", "b.exe"]) is None


@pytest.mark.parametrize("answer", ["0", "-1", "9", "banana"])
def test_choose_path_rejects_bad_input(monkeypatch, answer):
    """0 used to index the list from the end and silently pick the last hit."""
    monkeypatch.setattr("builtins.input", lambda *a: answer)
    with pytest.raises(SystemExit):
        q._choose_path(["a.exe", "b.exe"])


# -------------------------------------------------------------- quickstart

def _qs_args(**kw):
    base = dict(apps=None, ui=False, no_ui=False, area=None,
                force=False, dry_run=True, yes=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_ui_with_area_opens_the_picker_preselected(monkeypatch):
    """--ui used to be ignored whenever --area was also given."""
    seen = {}

    def fake_picker(initial=None, title=""):
        seen["initial"] = initial
        return None  # user cancels, so nothing is scanned or written

    monkeypatch.setattr(q, "_select_quickstart_categories", fake_picker)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(sys, "stdout", _Tty())

    q.cmd_quickstart(_qs_args(ui=True, area=["work"]))

    assert seen["initial"] == {"work"}


def test_area_alone_still_skips_the_picker(monkeypatch):
    def fail(*a, **kw):
        raise AssertionError("picker should not open for a bare --area")

    monkeypatch.setattr(q, "_select_quickstart_categories", fail)
    monkeypatch.setattr(q, "_build_quickstart_plan", lambda *a, **kw: ([], []))
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(sys, "stdout", _Tty())

    q.cmd_quickstart(_qs_args(area=["work"]))


def test_ui_and_no_ui_are_mutually_exclusive():
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "quickrun.py"),
         "quickstart", "--ui", "--no-ui"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not allowed with" in result.stderr


# ------------------------------------------------------------------ basics

@pytest.mark.parametrize("raw, expected", [
    ("Word", "word"),
    ("  word  ", "word"),
    ("winword.exe", "winword"),
    ("has space", None),
    ("has/slash", None),
    ("has:colon", None),
    ("", None),
])
def test_clean_alias(raw, expected):
    assert q._clean_alias(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("v0.6.1", (0, 6, 1)),
    ("0.6.1", (0, 6, 1)),
    ("v0.10.0", (0, 10, 0)),
])
def test_version_tuple(raw, expected):
    assert q._version_tuple(raw) == expected


def test_release_ordering_is_numeric_not_lexicographic():
    assert q._version_tuple("v0.10.0") > q._version_tuple("v0.6.1")
