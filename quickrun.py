#!/usr/bin/env python3
"""quickrun - bind custom Win+R aliases to any program.

Windows resolves anything typed into Win+R against the "App Paths"
registry key. Entries under HKCU need no admin rights and take effect
immediately. quickrun manages entries there and tags its own with a
marker value so it never deletes bindings it didn't create.
"""

import argparse
import codecs
import os
import re
import shutil
import sys
import time

if sys.platform != "win32":
    sys.exit("quickrun only works on Windows.")

import winreg

__version__ = "0.6.1"
GITHUB_REPO = "Unknownuserfrommars/quickrun"

APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
MARKER = "QuickRunManaged"
SOURCE_MARKER = "QuickRunSource"
ALIAS_OF_MARKER = "QuickRunAliasOf"


# ---------------------------------------------------------------- registry

def _subkey(alias: str) -> str:
    return rf"{APP_PATHS}\{alias}.exe"


def _read_value(root, subkey, name):
    """Return a registry value, or None if the key/value is missing."""
    try:
        with winreg.OpenKey(root, subkey) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def _read_default(root, subkey):
    """Return the default value of a key, or None if the key is missing."""
    return _read_value(root, subkey, "")


def _is_managed(alias: str) -> bool:
    return _read_value(winreg.HKEY_CURRENT_USER, _subkey(alias), MARKER) is not None


def _binding_source(alias: str):
    return _read_value(winreg.HKEY_CURRENT_USER, _subkey(alias), SOURCE_MARKER)


def _user_bindings():
    rows = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_PATHS) as key:
            count = winreg.QueryInfoKey(key)[0]
            names = [winreg.EnumKey(key, i) for i in range(count)]
    except OSError:
        names = []

    for name in names:
        alias = name[:-4] if name.lower().endswith(".exe") else name
        target = _read_default(winreg.HKEY_CURRENT_USER, rf"{APP_PATHS}\{name}")
        rows.append((alias, target or "(no target)",
                     _is_managed(alias), _binding_source(alias)))
    return rows


def _delete_value_if_present(key, name) -> None:
    try:
        winreg.DeleteValue(key, name)
    except OSError:
        pass


def resolve_alias(alias: str):
    """Return (target, source) if the alias already resolves somewhere."""
    for root, source in (
        (winreg.HKEY_CURRENT_USER, "user App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, "system App Paths"),
    ):
        target = _read_default(root, _subkey(alias))
        if target:
            return target, source
    # Things like notepad/powershell resolve through the system PATH.
    on_path = shutil.which(alias)
    if on_path:
        return on_path, "system PATH"
    return None, None


def _clean_alias(alias: str):
    """Return the normalized alias, or None if it's invalid."""
    alias = alias.strip().lower()
    if alias.endswith(".exe"):
        alias = alias[:-4]
    if not alias or any(c in alias for c in ' \\/:*?"<>|'):
        return None
    return alias


def normalize_alias(alias: str) -> str:
    cleaned = _clean_alias(alias)
    if cleaned is None:
        sys.exit(f'[!] "{alias}" is not a valid alias '
                 "(no spaces or \\ / : * ? \" < > | characters).")
    return cleaned


# ---------------------------------------------------------------- commands

def cmd_bind(args) -> None:
    alias = args.alias or args.alias_opt
    if not alias:
        sys.exit("[!] Missing alias. Usage: quickrun bind <exe> <alias>")
    alias = normalize_alias(alias)

    exe = os.path.abspath(os.path.expandvars(os.path.expanduser(args.exe)))
    if not os.path.isfile(exe):
        sys.exit(f"[!] File not found: {exe}")

    existing, source = resolve_alias(alias)
    if existing and not args.force:
        managed = " (created by quickrun)" if _is_managed(alias) else ""
        sys.exit(f'[!] "{alias}" already resolves to {existing} '
                 f"via {source}{managed}. Use --force to overwrite.")

    _write_binding(alias, exe, source="bind")
    print(f'[OK] Win+R -> "{alias}" now opens {exe}')


def _write_binding(alias: str, exe: str, source: str = "bind",
                   alias_of: str = None) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, _subkey(alias), 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, exe)
        winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, os.path.dirname(exe))
        winreg.SetValueEx(key, MARKER, 0, winreg.REG_SZ, "1")
        winreg.SetValueEx(key, SOURCE_MARKER, 0, winreg.REG_SZ, source)
        _delete_value_if_present(key, ALIAS_OF_MARKER)
        if alias_of:
            winreg.SetValueEx(key, ALIAS_OF_MARKER, 0, winreg.REG_SZ, alias_of)


def _resolve_command_target(command: str):
    maybe_path = os.path.abspath(os.path.expandvars(os.path.expanduser(command)))
    if os.path.isfile(maybe_path):
        return maybe_path, "path"

    cleaned = _clean_alias(command)
    if cleaned is None:
        sys.exit(f'[!] "{command}" is not a command name or existing file.')

    target, source = resolve_alias(cleaned)
    if not target:
        sys.exit(f'[!] "{command}" does not resolve through App Paths or PATH.')

    target = os.path.abspath(
        os.path.expandvars(os.path.expanduser(target.strip('"')))
    )
    if not os.path.isfile(target):
        sys.exit(f'[!] "{command}" resolves to {target}, but that file '
                 "does not exist.")
    return target, source


def _delete_binding(alias: str, force: bool = False):
    target = _read_default(winreg.HKEY_CURRENT_USER, _subkey(alias))
    if target is None:
        return None
    if not _is_managed(alias) and not force:
        sys.exit(f'[!] "{alias}" exists but was not created by quickrun. '
                 "Use --force to delete it anyway.")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _subkey(alias))
    return target


def _print_remove_plan(rows, heading: str) -> None:
    print(heading)
    width = max(len(r[0]) for r in rows)
    for alias, target, managed, source in sorted(rows):
        tags = []
        if not managed:
            tags.append("external")
        elif source:
            tags.append(source)
        tag = f"  [{', '.join(tags)}]" if tags else ""
        print(f"  {alias:<{width}}  ->  {target}{tag}")


def _remove_many(rows, args, empty_message: str) -> None:
    if not rows:
        print(empty_message)
        return

    _print_remove_plan(rows, "Will remove:")
    if args.dry_run:
        print("\n(dry run - nothing deleted)")
        return

    if not args.yes:
        answer = input(f"\nDelete {len(rows)} binding(s)? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return

    for alias, _, _, _ in rows:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _subkey(alias))
    print(f"\n[OK] Removed {len(rows)} binding(s).")


# --------------------------------------------- terminal (PowerShell) aliases

PROFILE_MARK = "# QuickRunManaged"
_PROFILE_LINE = re.compile(
    r"^\s*Set-Alias\s+-Name\s+(\S+)\s+-Value\s+'((?:[^']|'')*)'\s*"
    + re.escape(PROFILE_MARK) + r"\s*$",
    re.IGNORECASE,
)


def _documents_dir() -> str:
    # The Documents folder is often redirected (OneDrive); the registry
    # has the real location.
    val = _read_value(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        "Personal",
    )
    if val:
        return os.path.expandvars(val)
    return os.path.expandvars(r"%UserProfile%\Documents")


def _profile_targets():
    """(profile.ps1, shell exe) for Windows PowerShell 5.1 and PowerShell 7+."""
    docs = _documents_dir()
    return [(os.path.join(docs, "WindowsPowerShell", "profile.ps1"), "powershell"),
            (os.path.join(docs, "PowerShell", "profile.ps1"), "pwsh")]


def _profile_paths():
    """profile.ps1 for both Windows PowerShell 5.1 and PowerShell 7+."""
    return [path for path, _ in _profile_targets()]


def _profile_encoding(data: bytes):
    """Return the encoding a profile's BOM names, or None if it has none."""
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    # PowerShell 5.1 can leave a BOM-less UTF-16 profile behind. Its ASCII
    # is every other byte NUL, which is valid UTF-8 and would otherwise
    # decode to mojibake that we then write back over the real profile.
    if b"\x00" in data[:64]:
        return "utf-16-le" if data[1:2] == b"\x00" else "utf-16-be"
    return None


def _read_profile(path):
    with open(path, "rb") as f:
        data = f.read()
    # A BOM is authoritative - never fall back past it, or a decode that
    # merely *succeeds* (cp1252 happily reads UTF-16 as mojibake) would
    # corrupt the file on write.
    declared = _profile_encoding(data)
    for encoding in [declared] if declared else ["utf-8", "mbcs"]:
        try:
            return data.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    sys.exit(f"[!] Could not decode {path}; edit it manually.")


def _profile_aliases(path):
    """Return {alias: value} for quickrun-managed Set-Alias lines."""
    if not os.path.isfile(path):
        return {}
    text, _ = _read_profile(path)
    found = {}
    for line in text.splitlines():
        match = _PROFILE_LINE.match(line)
        if match:
            found[match.group(1).lower()] = match.group(2).replace("''", "'")
    return found


def _dominant_newline(text: str) -> str:
    crlf = text.count("\r\n")
    return "\n" if text.count("\n") - crlf > crlf else "\r\n"


def _keep_lines(text: str, alias: str):
    """Existing lines minus this alias, each with its own ending intact."""
    return [l for l in text.splitlines(keepends=True)
            if not _is_alias_line(l, alias)]


def _is_alias_line(line: str, alias: str) -> bool:
    match = _PROFILE_LINE.match(line)
    return bool(match) and match.group(1).lower() == alias


def _add_cmd_alias(alias: str, value: str):
    """Write the Set-Alias line; return the profiles it landed in."""
    quoted = value.replace("'", "''")
    line = f"Set-Alias -Name {alias} -Value '{quoted}' {PROFILE_MARK}"
    written = []
    for path, shell in _profile_targets():
        if os.path.isfile(path):
            text, encoding = _read_profile(path)
            eol = _dominant_newline(text)
            lines = _keep_lines(text, alias)
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += eol
            lines.append(line + eol)
            content = "".join(lines)
        elif shutil.which(shell):
            # Only create a profile for a shell that is actually installed.
            os.makedirs(os.path.dirname(path), exist_ok=True)
            content, encoding = line + "\r\n", "utf-8-sig"
        else:
            continue
        # newline="" so we never rewrite line endings we did not author.
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(content)
        written.append(path)
    return written


def _remove_cmd_alias(alias: str):
    """Delete the managed Set-Alias line; return profiles it was removed from."""
    removed = []
    for path in _profile_paths():
        if alias not in _profile_aliases(path):
            continue
        text, encoding = _read_profile(path)
        content = "".join(_keep_lines(text, alias))
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(content)
        removed.append(path)
    return removed


def _cmd_alias_exists(alias: str) -> bool:
    return any(alias in _profile_aliases(p) for p in _profile_paths())


def cmd_alias(args) -> None:
    new_alias = normalize_alias(args.new_alias)
    old_display = args.old_cmd

    if _clean_alias(args.old_cmd) == new_alias:
        sys.exit("[!] old_cmd and new_alias are the same.")

    if args.cmd:
        # Terminal alias: persisted as a Set-Alias line in the PowerShell
        # profiles, which run at every shell startup (Set-Alias alone
        # only lasts for one session).
        if shutil.which(args.old_cmd):
            value = args.old_cmd  # on PATH; keep the name, survives moves
        else:
            # Terminals don't resolve App Paths names - pin the full path.
            value, _ = _resolve_command_target(args.old_cmd)
        conflict = shutil.which(new_alias)
        if conflict and not args.force:
            sys.exit(f'[!] "{new_alias}" is already a command ({conflict}). '
                     "Use --force to shadow it.")
        if _cmd_alias_exists(new_alias) and not args.force:
            sys.exit(f'[!] Terminal alias "{new_alias}" already exists. '
                     "Use --force to replace it.")
        written = _add_cmd_alias(new_alias, value)
        if not written:
            sys.exit("[!] Found no PowerShell profile to write to, and "
                     "neither powershell nor pwsh is on PATH.")
        print(f'[OK] Terminal alias "{new_alias}" -> {value} added to:')
        for path in written:
            print(f"       {path}")
        print("     Takes effect in NEW terminal windows "
              "(or run: . $PROFILE)")
        return

    target, source = _resolve_command_target(args.old_cmd)

    existing, existing_source = resolve_alias(new_alias)
    if existing and not args.force:
        managed = " (created by quickrun)" if _is_managed(new_alias) else ""
        sys.exit(f'[!] "{new_alias}" already resolves to {existing} '
                 f"via {existing_source}{managed}. Use --force to overwrite.")

    _write_binding(new_alias, target, source="alias", alias_of=old_display)
    print(f'[OK] Win+R -> "{new_alias}" now opens {target} '
          f'(alias of "{old_display}" via {source})')


def cmd_del_alias(args) -> None:
    """Removes a quickrun alias of either kind: Win+R or terminal."""
    alias = normalize_alias(args.alias)
    target = _read_default(winreg.HKEY_CURRENT_USER, _subkey(alias))
    source = _binding_source(alias)
    reg_removable = target is not None and (args.force or source == "alias")
    has_cmd = _cmd_alias_exists(alias)

    if args.dry_run:
        if reg_removable:
            print(f'[dry run] Would remove Win+R alias "{alias}" -> {target}')
        elif target is not None:
            print(f'[dry run] Would not remove Win+R binding "{alias}" - it '
                  "was not created by quickrun alias (use unbind, or --force).")
        if has_cmd:
            print(f'[dry run] Would remove terminal alias "{alias}" from '
                  "your PowerShell profiles.")
        if target is None and not has_cmd:
            print(f'[dry run] No alias named "{alias}".')
        return

    removed_any = False
    if reg_removable:
        _delete_binding(alias, args.force)
        print(f'[OK] Removed Win+R alias "{alias}" (was {target})')
        removed_any = True
    if has_cmd:
        for path in _remove_cmd_alias(alias):
            print(f'[OK] Removed terminal alias "{alias}" from {path}')
        print("     Open terminals keep it until restarted "
              f"(or run: Remove-Alias {alias})")
        removed_any = True

    if not removed_any:
        if target is not None:
            sys.exit(f'[!] "{alias}" was not created by quickrun alias. '
                     "Use quickrun unbind instead, or --force.")
        sys.exit(f'[!] No alias named "{alias}".')


def cmd_unbind(args) -> None:
    if args.alias.strip().lower() == "all":
        rows = [row for row in _user_bindings() if row[2] or args.force]
        _remove_many(rows, args, "No quickrun-managed bindings to remove.")
        return

    alias = normalize_alias(args.alias)
    if args.dry_run:
        target = _read_default(winreg.HKEY_CURRENT_USER, _subkey(alias))
        if target is None:
            print(f'[dry run] No user-level binding for "{alias}".')
        else:
            print(f'[dry run] Would remove "{alias}" -> {target}')
        return

    target = _delete_binding(alias, args.force)
    if target is None:
        sys.exit(f'[!] No user-level binding for "{alias}".')
    print(f'[OK] Removed "{alias}" (was {target})')


def cmd_list(args) -> None:
    rows = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_PATHS) as key:
            count = winreg.QueryInfoKey(key)[0]
            names = [winreg.EnumKey(key, i) for i in range(count)]
    except OSError:
        names = []

    for name in names:
        alias = name[:-4] if name.lower().endswith(".exe") else name
        target = _read_default(winreg.HKEY_CURRENT_USER, rf"{APP_PATHS}\{name}")
        managed = _is_managed(alias)
        if managed or args.all:
            rows.append((alias, target or "(no target)", managed))

    cmd_aliases = {}
    for path in _profile_paths():
        for alias, value in _profile_aliases(path).items():
            cmd_aliases[alias] = value

    if not rows and not cmd_aliases:
        print("No bindings yet. Try: quickrun bind <path\\to\\app.exe> <alias>")
        print("Or auto-detect installed apps: quickrun quickstart")
        return

    if rows:
        width = max(len(r[0]) for r in rows)
        for alias, target, managed in sorted(rows):
            tag = "" if managed else "  [external]"
            print(f"  {alias:<{width}}  ->  {target}{tag}")

    if cmd_aliases:
        print("\nTerminal aliases (PowerShell profiles):")
        width = max(len(a) for a in cmd_aliases)
        for alias, value in sorted(cmd_aliases.items()):
            print(f"  {alias:<{width}}  ->  {value}")

    if not args.all:
        print("\n(only quickrun-managed bindings shown; use --all for every "
              "user-level App Paths entry)")


# ---------------------------------------------------------------- quickstart

def _from_app_paths(exe_name):
    """Find an app Windows already registered (Office does this on install)."""
    def find():
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            target = _read_default(root, rf"{APP_PATHS}\{exe_name}")
            if target and os.path.isfile(target.strip('"')):
                return target.strip('"')
        return None
    return find


def _from_paths(*candidates):
    """Find an app by checking known install locations."""
    def find():
        for candidate in candidates:
            path = os.path.expandvars(candidate)
            if os.path.isfile(path):
                return path
        return None
    return find


def _from_commands(*commands):
    """Find a command already on PATH."""
    def find():
        for command in commands:
            path = shutil.which(command)
            if path and os.path.isfile(path):
                return path
        return None
    return find


def _first_found(*finders):
    def find():
        for finder in finders:
            path = finder()
            if path:
                return path
        return None
    return find


PF = r"%ProgramFiles%"
PF86 = r"%ProgramFiles(x86)%"
LOCAL = r"%LocalAppData%"
ROAM = r"%AppData%"

QUICKSTART_CATEGORIES = [
    ("work", "Working", "Word, Excel, PowerPoint, Outlook, OneNote, Access"),
    ("browsers", "Browsers", "Chrome, Firefox"),
    ("coding", "Coding & AI", "VS Code, Notepad++, Claude, Codex, Cursor"),
    ("utilities", "Utilities", "7-Zip"),
    ("media", "Media & Games", "VLC, Steam, Spotify"),
    ("chat", "Chat", "Telegram, WeChat, QQ"),
]

QUICKSTART_APPS = [
    # (category, display name, aliases, finder)
    ("work", "Microsoft Word",       ["word", "msword"],   _from_app_paths("winword.exe")),
    ("work", "Microsoft Excel",      ["excel"],            _from_app_paths("excel.exe")),
    ("work", "Microsoft PowerPoint", ["powerpoint", "ppt"], _from_app_paths("powerpnt.exe")),
    ("work", "Microsoft Outlook",    ["outlook"],          _from_app_paths("outlook.exe")),
    ("work", "Microsoft OneNote",    ["onenote"],          _from_app_paths("onenote.exe")),
    ("work", "Microsoft Access",     ["access"],           _from_app_paths("msaccess.exe")),
    ("browsers", "Google Chrome",    ["chrome"],
        _from_paths(rf"{PF}\Google\Chrome\Application\chrome.exe",
                    rf"{PF86}\Google\Chrome\Application\chrome.exe",
                    rf"{LOCAL}\Google\Chrome\Application\chrome.exe")),
    ("browsers", "Mozilla Firefox",  ["firefox"],
        _from_paths(rf"{PF}\Mozilla Firefox\firefox.exe")),
    ("coding", "VS Code",            ["vscode"],
        _from_paths(rf"{LOCAL}\Programs\Microsoft VS Code\Code.exe",
                    rf"{PF}\Microsoft VS Code\Code.exe")),
    ("coding", "Notepad++",          ["npp"],
        _from_paths(rf"{PF}\Notepad++\notepad++.exe",
                    rf"{PF86}\Notepad++\notepad++.exe")),
    ("coding", "Claude",             ["claude"],
        _first_found(_from_app_paths("claude.exe"),
                     _from_paths(rf"{LOCAL}\AnthropicClaude\Claude.exe",
                                 rf"{LOCAL}\Programs\Claude\Claude.exe",
                                 rf"{PF}\Claude\Claude.exe"),
                     _from_commands("claude", "claude.exe", "claude.cmd"))),
    ("coding", "Codex",              ["codex"],
        _first_found(_from_app_paths("codex.exe"),
                     _from_commands("codex", "codex.exe", "codex.cmd"))),
    ("coding", "Cursor",             ["cursor"],
        _from_paths(rf"{LOCAL}\Programs\Cursor\Cursor.exe",
                    rf"{PF}\Cursor\Cursor.exe")),
    ("utilities", "7-Zip",           ["7z"],
        _from_paths(rf"{PF}\7-Zip\7zFM.exe")),
    ("media", "VLC",                 ["vlc"],
        _from_paths(rf"{PF}\VideoLAN\VLC\vlc.exe",
                    rf"{PF86}\VideoLAN\VLC\vlc.exe")),
    ("media", "Steam",               ["steam"],
        _from_paths(rf"{PF86}\Steam\steam.exe", rf"{PF}\Steam\steam.exe")),
    ("media", "Spotify",             ["spotify"],
        _from_paths(rf"{ROAM}\Spotify\Spotify.exe")),
    ("chat", "Telegram",             ["telegram", "tg"],
        _from_paths(rf"{ROAM}\Telegram Desktop\Telegram.exe")),
    ("chat", "WeChat",               ["wechat", "wx"],
        _from_paths(rf"{PF}\Tencent\Weixin\Weixin.exe",
                    rf"{PF}\Tencent\WeChat\WeChat.exe",
                    rf"{PF86}\Tencent\WeChat\WeChat.exe")),
    ("chat", "QQ",                   ["qq"],
        _from_paths(rf"{PF}\Tencent\QQNT\QQ.exe",
                    rf"{PF86}\Tencent\QQ\Bin\QQ.exe")),
]


CUSTOM_ROW = ("custom", "Custom apps",
              "type names yourself, e.g. telegram, obsidian, notion")


def _quickstart_category_keys():
    return [key for key, _, _ in QUICKSTART_CATEGORIES]


def _picker_rows():
    return QUICKSTART_CATEGORIES + [CUSTOM_ROW]


def _quickstart_apps(categories=None):
    selected = set(categories) if categories is not None else None
    for category, display, aliases, find in QUICKSTART_APPS:
        if selected is None or category in selected:
            yield category, display, aliases, find


_ANSI = {
    "reset": "\x1b[0m",
    "bold": "\x1b[1m",
    "dim": "\x1b[2m",
    "cyan": "\x1b[36m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "reverse": "\x1b[7m",
    "clear": "\x1b[2J\x1b[H",
    "hide": "\x1b[?25l",
    "show": "\x1b[?25h",
}


def _enable_ansi() -> None:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _read_key():
    import msvcrt
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        code = msvcrt.getwch()
        return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(code)
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "space"
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch.lower()


def _draw_quickstart_picker(index, selected, title) -> None:
    out = sys.stdout
    out.write(_ANSI["clear"])
    out.write(_ANSI["hide"])
    out.write(f'{_ANSI["bold"]}{_ANSI["cyan"]}quickrun quickstart{_ANSI["reset"]}\n')
    out.write(f"{title}\n\n")
    out.write("Space toggles, Up/Down moves, Enter continues, "
              "A toggles all areas, Q cancels.\n\n")

    for i, (key, label, description) in enumerate(_picker_rows()):
        active = i == index
        checked = key in selected
        cursor = ">" if active else " "
        box = "x" if checked else " "
        color = _ANSI["reverse"] if active else ""
        tick = _ANSI["green"] if checked else _ANSI["dim"]
        out.write(f"{color}{cursor} {tick}[{box}]{_ANSI['reset']} "
                  f"{label:<14} {description}{_ANSI['reset']}\n")

    out.write(f"\n{_ANSI['yellow']}{len(selected)} selected"
              f"{_ANSI['reset']}\n")
    out.flush()


def _select_quickstart_categories(initial=None, title="Select app areas"):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.exit("[!] --ui needs an interactive console.")

    rows = _picker_rows()
    selected = set(initial) if initial is not None else set()
    index = 0
    _enable_ansi()
    try:
        while True:
            _draw_quickstart_picker(index, selected, title)
            key = _read_key()
            if key == "up":
                index = (index - 1) % len(rows)
            elif key == "down":
                index = (index + 1) % len(rows)
            elif key == "space":
                row_key = rows[index][0]
                if row_key in selected:
                    selected.remove(row_key)
                else:
                    selected.add(row_key)
            elif key == "a":
                all_keys = set(_quickstart_category_keys())
                if all_keys <= selected:
                    selected -= all_keys
                else:
                    selected |= all_keys
            elif key == "enter":
                return selected
            elif key in ("q", "\x1b"):
                return None
    except KeyboardInterrupt:
        return None
    finally:
        sys.stdout.write(_ANSI["show"] + _ANSI["reset"] + "\n")
        sys.stdout.flush()


def _build_quickstart_plan(args, categories=None):
    plan = []      # (alias, exe, display)
    skipped = []   # (alias, reason)

    for _, display, aliases, find in _quickstart_apps(categories):
        exe = find()
        if not exe:
            continue
        for alias in aliases:
            existing, source = resolve_alias(alias)
            if existing and not args.force:
                if _is_managed(alias):
                    skipped.append((alias, "already bound by quickrun"))
                else:
                    skipped.append((alias, f"already taken via {source}"))
                continue
            plan.append((alias, exe, display))
    return plan, skipped


def _split_apps(raw):
    return [name.strip() for name in (raw or "").split(",") if name.strip()]


def _find_custom_apps(names, args):
    """Run a quick find for each user-typed app name."""
    plan, skipped, missing = [], [], []
    for name in names:
        alias = _clean_alias(name)
        if alias is None:
            skipped.append((name, "not a valid alias name"))
            continue
        print(f'  looking for "{name}" ...')
        exact, partial, _ = _find_candidates(name, budget=6.0)
        hits = exact or partial
        if not hits:
            missing.append(name)
            continue
        existing, source = resolve_alias(alias)
        if existing and not args.force:
            if _is_managed(alias):
                skipped.append((alias, "already bound by quickrun"))
            else:
                skipped.append((alias, f"already taken via {source}"))
            continue
        if len(hits) > 1 and sys.stdin.isatty() and sys.stdout.isatty():
            print(f'  several matches for "{name}":')
            chosen = _choose_path(hits[:10], indent="    ")
            if chosen is None:
                skipped.append((alias, "no candidate chosen"))
                continue
        else:
            chosen = hits[0]
        plan.append((alias, chosen, name))
    return plan, skipped, missing


def cmd_quickstart(args) -> None:
    custom_apps = _split_apps(args.apps)
    interactive = sys.stdin.isatty() and sys.stdout.isatty()

    if args.ui and not interactive:
        sys.exit("[!] --ui needs an interactive console.")

    categories = None  # None = scan every area
    use_ui = args.ui or (interactive and not args.no_ui and not args.area)
    if use_ui:
        selected = _select_quickstart_categories(
            set(args.area) if args.area else set(),
            "Select what quickstart should look for."
        )
        if selected is None:
            print("Cancelled.")
            return
        if "custom" in selected:
            selected.discard("custom")
            try:
                raw = input("Apps to look for (comma-separated, "
                            "e.g. telegram, obsidian, notion): ")
            except EOFError:
                raw = ""
            custom_apps += _split_apps(raw)
        categories = selected
    elif args.area:
        categories = set(args.area)
    elif custom_apps:
        categories = set()  # --apps without --area: just the typed apps

    if categories == set() and not custom_apps:
        print("Nothing selected.")
        return

    print("Scanning for installed apps...\n")
    plan, skipped = _build_quickstart_plan(args, categories)
    missing = []
    if custom_apps:
        custom_plan, custom_skipped, missing = _find_custom_apps(
            custom_apps, args)
        plan += custom_plan
        skipped += custom_skipped
        print()

    if plan:
        width = max(len(a) for a, _, _ in plan)
        print("Found - will bind:")
        for alias, exe, display in plan:
            print(f"  {alias:<{width}}  ->  {exe}")
    if missing:
        print("\nNot found: " + ", ".join(missing))
        print("  (try the exe's real name, or a deeper interactive "
              "search: quickrun find <name>)")
    if skipped:
        print("\nSkipped:")
        for alias, reason in skipped:
            print(f"  {alias}: {reason}")
    if not plan:
        print("\nNothing new to bind.")
        return

    if args.dry_run:
        print("\n(dry run - nothing written)")
        return

    if not args.yes:
        answer = input(f"\nBind the {len(plan)} alias(es) found? "
                       "[Y/n] ").strip().lower()
        if answer not in ("", "y", "yes"):
            print("Cancelled.")
            return

    for alias, exe, _ in plan:
        _write_binding(alias, exe, source="quickstart")
    print(f"\n[OK] {len(plan)} alias(es) bound. "
          "Try Win+R and type one of them.")


# ---------------------------------------------------------------- find

_UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
]

# Directories that are huge and never contain user-facing exes.
_SKIP_DIRS = {
    "windows", "winsxs", "temp", "tmp", "cache", "caches", "logs",
    "node_modules", "__pycache__", "packages", "assembly", "installer",
    "servicing", "locales", "resources", "$recycle.bin",
}

# (root, max scan depth) - deeper where installs actually live.
def _search_roots():
    roots = [
        (os.environ.get("ProgramFiles", r"C:\Program Files"), 4),
        (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), 4),
        (os.path.expandvars(r"%LocalAppData%\Programs"), 4),
        (os.path.expandvars(r"%AppData%"), 3),
        (os.path.expandvars(r"%LocalAppData%"), 3),
        (os.path.expandvars(r"%UserProfile%\scoop\apps"), 3),
        (os.environ.get("ProgramData", r"C:\ProgramData"), 2),
    ]
    return [(r, d) for r, d in roots if r and os.path.isdir(r)]


def _find_candidates(query: str, budget: float = 10.0):
    """Return (exact_hits, partial_hits) for query, fast-paths first."""
    query = query.strip().lower()
    if not query:
        return [], [], False
    if not query.endswith(".exe"):
        query += ".exe"
    stem = query[:-4]
    deadline = time.time() + budget

    exact, partial, seen = [], [], set()

    def add(bucket, path):
        path = os.path.abspath(
            os.path.expandvars(os.path.expanduser(path.strip('"')))
        )
        key = os.path.normcase(path)
        if key not in seen and os.path.isfile(path):
            seen.add(key)
            bucket.append(path)

    # 1. App Paths entries (instant).
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        target = _read_default(root, rf"{APP_PATHS}\{query}")
        if target:
            add(exact, target)

    # 2. Installer registry: DisplayIcon usually points at the main exe.
    for root, base in _UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(root, base) as key:
                names = [winreg.EnumKey(key, i)
                         for i in range(winreg.QueryInfoKey(key)[0])]
        except OSError:
            continue
        for name in names:
            try:
                with winreg.OpenKey(root, rf"{base}\{name}") as sub:
                    icon, _ = winreg.QueryValueEx(sub, "DisplayIcon")
            except OSError:
                continue
            exe = icon.split(",")[0].strip().strip('"')
            base_name = os.path.basename(exe).lower()
            if base_name == query:
                add(exact, exe)
            elif base_name.endswith(".exe") and stem in base_name:
                add(partial, exe)

    # 3. PATH.
    on_path = shutil.which(query)
    if on_path:
        add(exact, on_path)

    # 4. Depth-limited scan of the usual install locations.
    for root, max_depth in _search_roots():
        stack = [(root, 0)]
        while stack:
            if time.time() > deadline:
                return exact, partial, True
            path, depth = stack.pop()
            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        try:
                            name = entry.name.lower()
                            if entry.is_file():
                                if name == query:
                                    add(exact, entry.path)
                                elif name.endswith(".exe") and stem in name:
                                    add(partial, entry.path)
                            elif (depth < max_depth
                                  and name not in _SKIP_DIRS
                                  and entry.is_dir(follow_symlinks=False)):
                                stack.append((entry.path, depth + 1))
                        except OSError:
                            pass
            except OSError:
                pass

    return exact, partial, False


def _choose_path(hits, indent="  "):
    """Ask which candidate exe to use; None if the user cancels."""
    for i, path in enumerate(hits, 1):
        print(f"{indent}[{i}] {path}")
    try:
        answer = input(f"\nWhich one? [1-{len(hits)}, Enter to cancel] ").strip()
    except EOFError:
        answer = ""
    if not answer:
        return None
    try:
        index = int(answer)
        if index < 1:
            raise IndexError
        return hits[index - 1]
    except (ValueError, IndexError):
        sys.exit(f'[!] "{answer}" is not a number between 1 and {len(hits)}.')


def cmd_find(args) -> None:
    query = args.name.strip()
    if not query:
        sys.exit("[!] Missing name. Usage: quickrun find <name>")
    print(f'Searching for "{query}" ...')
    start = time.time()
    exact, partial, timed_out = _find_candidates(query)
    elapsed = time.time() - start

    hits = exact or partial[:10]
    label = "" if exact else " (no exact match; closest names)"
    note = ", search budget hit - results may be incomplete" if timed_out else ""
    print(f"{len(hits)} result(s) in {elapsed:.1f}s{label}{note}\n")

    if not hits:
        print("Nothing found. Tips: use the real exe name (e.g. winword, "
              "not word),\nor bind the path directly: quickrun bind <path> <alias>")
        return

    if len(hits) == 1:
        chosen = hits[0]
        print(f"  Found: {chosen}")
    else:
        chosen = _choose_path(hits)
        if chosen is None:
            print("Cancelled.")
            return

    while True:
        try:
            raw = input("Alias to bind it to (press Enter to skip): ").strip()
        except EOFError:
            raw = ""
        if not raw:
            print("Skipped - nothing was bound.")
            return
        alias = _clean_alias(raw)
        if alias is None:
            print(f'  "{raw}" is not valid (no spaces or \\ / : * ? " < > |). '
                  "Try again.")
            continue
        existing, source = resolve_alias(alias)
        if existing:
            print(f'  "{alias}" already resolves to {existing} via {source}. '
                  "Pick another name.")
            continue
        _write_binding(alias, chosen, source="find")
        print(f'[OK] Win+R -> "{alias}" now opens {chosen}')
        return


# ---------------------------------------------------------------- update

def _version_tuple(version: str):
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def cmd_update(args) -> None:
    """Self-update by downloading quickrun.exe from the latest release.

    A running exe on Windows can be renamed but not overwritten, so the
    current file is parked as quickrun.exe.old and cleaned up next run.
    """
    if not getattr(sys, "frozen", False):
        sys.exit("[!] update only works for the standalone quickrun.exe.\n"
                 "    Running from source? Use: git pull")

    import hashlib
    import json
    import urllib.request

    def fetch(url, **kw):
        req = urllib.request.Request(url, headers={"User-Agent": "quickrun"})
        return urllib.request.urlopen(req, **kw)

    api = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        with fetch(api, timeout=15) as resp:
            release = json.load(resp)
    except OSError as exc:
        sys.exit(f"[!] Could not check for updates: {exc}")

    latest = release.get("tag_name", "v0")
    if _version_tuple(latest) <= _version_tuple(__version__):
        print(f"[OK] quickrun {__version__} is up to date.")
        return

    asset = next((a for a in release.get("assets", [])
                  if a["name"].lower() == "quickrun.exe"), None)
    if not asset:
        sys.exit(f"[!] Release {latest} has no quickrun.exe attached.")

    exe = sys.executable
    print(f"Updating {__version__} -> {latest.lstrip('v')} ...")
    tmp = exe + ".new"
    digest, size = hashlib.sha256(), 0
    try:
        with fetch(asset["browser_download_url"], timeout=120) as resp, \
                open(tmp, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
    except OSError as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(f"[!] Download failed: {exc}")

    # A truncated or tampered download must never replace a working exe.
    expected_size = asset.get("size")
    expected_hash = (asset.get("digest") or "").partition("sha256:")[2].lower()
    problem = None
    if expected_size and size != expected_size:
        problem = f"expected {expected_size} bytes, got {size}"
    elif expected_hash and digest.hexdigest() != expected_hash:
        problem = "sha256 does not match the release digest"
    if problem:
        os.remove(tmp)
        sys.exit(f"[!] Download verification failed ({problem}). "
                 "Your current quickrun.exe is untouched.")
    if not expected_hash:
        print("    (release publishes no sha256; verified size only)")

    old = exe + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.rename(exe, old)
    os.rename(tmp, exe)
    print(f"[OK] Updated to {latest.lstrip('v')}. "
          "(leftover .old file is removed on next run)")


def _cleanup_old_exe() -> None:
    if getattr(sys, "frozen", False):
        old = sys.executable + ".old"
        if os.path.exists(old):
            try:
                os.remove(old)
            except OSError:
                pass  # previous version still shutting down; next run gets it


# ---------------------------------------------------------------- cli

# Accept the single-dash spelling too: quickrun -bind ... / -b ...
_COMMAND_ALIASES = {
    "-bind": "bind", "-b": "bind", "b": "bind",
    "-unbind": "unbind", "-u": "unbind", "u": "unbind",
    "-list": "list", "-l": "list", "l": "list", "ls": "list",
    "-quickstart": "quickstart", "-q": "quickstart", "qs": "quickstart",
    "--update": "update", "-U": "update", "-update": "update", "up": "update",
    "-find": "find", "--find": "find", "f": "find",
    "-alias": "alias", "--alias": "alias", "a": "alias",
    "-del_alias": "del_alias", "--del_alias": "del_alias", "da": "del_alias",
}


def _pause_if_own_console() -> None:
    """When launched from Win+R/Explorer, the console vanishes the moment
    we exit - if it's ours alone, wait so the help stays readable."""
    try:
        import ctypes
        pids = (ctypes.c_uint * 2)()
        if ctypes.windll.kernel32.GetConsoleProcessList(pids, 2) <= 1:
            input("\nPress Enter to close...")
    except Exception:
        pass


def main() -> None:
    _cleanup_old_exe()
    argv = sys.argv[1:]
    if argv and argv[0] in _COMMAND_ALIASES:
        argv[0] = _COMMAND_ALIASES[argv[0]]

    parser = argparse.ArgumentParser(
        prog="quickrun",
        description="Bind custom Win+R aliases to any program. "
                    "No admin rights needed; changes apply instantly.",
    )
    parser.add_argument("-V", "--version", action="version",
                        version=f"quickrun {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_bind = sub.add_parser("bind", help="bind an alias to an exe")
    p_bind.add_argument("exe", help="path to the program")
    p_bind.add_argument("alias", nargs="?", help="name to type into Win+R")
    p_bind.add_argument("-a", "-alias", "--alias", dest="alias_opt",
                        help="alias (alternative to the positional form)")
    p_bind.add_argument("-f", "--force", action="store_true",
                        help="overwrite an existing binding")
    p_bind.set_defaults(func=cmd_bind)

    p_alias = sub.add_parser("alias",
                             help="make a permanent alias for a command")
    p_alias.add_argument("old_cmd", help="existing command, alias, or exe path")
    p_alias.add_argument("new_alias", help="new name to type into Win+R")
    p_alias.add_argument("--cmd", action="store_true",
                         help="make a terminal (PowerShell) alias instead of "
                              "a Win+R one, persisted via your profile")
    p_alias.add_argument("-f", "--force", action="store_true",
                         help="overwrite an existing binding")
    p_alias.set_defaults(func=cmd_alias)

    p_del_alias = sub.add_parser("del_alias", help="remove a quickrun alias")
    p_del_alias.add_argument("alias")
    p_del_alias.add_argument("-f", "--force", action="store_true",
                             help="also delete entries quickrun didn't create")
    p_del_alias.add_argument("-n", "--dry-run", action="store_true",
                             help="show what would be removed")
    p_del_alias.set_defaults(func=cmd_del_alias)

    p_unbind = sub.add_parser("unbind", help="remove a binding")
    p_unbind.add_argument("alias", help='alias to remove, or "all"')
    p_unbind.add_argument("-f", "--force", action="store_true",
                          help="also delete entries quickrun didn't create")
    p_unbind.add_argument("-n", "--dry-run", action="store_true",
                          help="show what would be removed")
    p_unbind.add_argument("-y", "--yes", action="store_true",
                          help='do not ask before "unbind all"')
    p_unbind.set_defaults(func=cmd_unbind)

    p_list = sub.add_parser("list", help="show current bindings")
    p_list.add_argument("--all", action="store_true",
                        help="include user-level entries not created by quickrun")
    p_list.set_defaults(func=cmd_list)

    p_qs = sub.add_parser("quickstart",
                          help="auto-detect installed apps and bind them")
    p_qs.add_argument("-y", "--yes", action="store_true",
                      help="bind without asking")
    p_qs.add_argument("-n", "--dry-run", action="store_true",
                      help="only show what would be bound")
    p_qs.add_argument("-f", "--force", action="store_true",
                      help="rebind aliases that already exist")
    p_qs_ui = p_qs.add_mutually_exclusive_group()
    p_qs_ui.add_argument("--ui", action="store_true",
                         help="force the interactive picker (it is already "
                              "the default in a console); with --area, opens "
                              "the picker with those areas preselected")
    p_qs_ui.add_argument("--no-ui", action="store_true",
                         help="skip the picker and scan every area")
    p_qs.add_argument("--area", action="append",
                      choices=_quickstart_category_keys(),
                      help="limit quickstart to an app area; can repeat "
                           "(skips the picker unless --ui is given)")
    p_qs.add_argument("--apps",
                      help="extra apps to look for, comma-separated: "
                           '--apps "telegram, obsidian, notion"')
    p_qs.set_defaults(func=cmd_quickstart)

    p_find = sub.add_parser(
        "find", help="search the computer for an exe and offer to bind it")
    p_find.add_argument("name", help='program to look for, e.g. "obsidian" '
                                     'or "everything.exe"')
    p_find.set_defaults(func=cmd_find)

    p_update = sub.add_parser(
        "update", help="update quickrun.exe to the latest GitHub release")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        _pause_if_own_console()
        return
    args.func(args)


if __name__ == "__main__":
    main()
