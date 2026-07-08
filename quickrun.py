#!/usr/bin/env python3
"""quickrun - bind custom Win+R aliases to any program.

Windows resolves anything typed into Win+R against the "App Paths"
registry key. Entries under HKCU need no admin rights and take effect
immediately. quickrun manages entries there and tags its own with a
marker value so it never deletes bindings it didn't create.
"""

import argparse
import os
import re
import shutil
import sys

if sys.platform != "win32":
    sys.exit("quickrun only works on Windows.")

import winreg

__version__ = "0.2.0"
GITHUB_REPO = "Unknownuserfrommars/quickrun"

APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
MARKER = "QuickRunManaged"


# ---------------------------------------------------------------- registry

def _subkey(alias: str) -> str:
    return rf"{APP_PATHS}\{alias}.exe"


def _read_default(root, subkey):
    """Return the default value of a key, or None if the key is missing."""
    try:
        with winreg.OpenKey(root, subkey) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return value
    except OSError:
        return None


def _is_managed(alias: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _subkey(alias)) as key:
            winreg.QueryValueEx(key, MARKER)
            return True
    except OSError:
        return False


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


def normalize_alias(alias: str) -> str:
    alias = alias.strip().lower()
    if alias.endswith(".exe"):
        alias = alias[:-4]
    if not alias or any(c in alias for c in ' \\/:*?"<>|'):
        sys.exit(f'[!] "{alias}" is not a valid alias '
                 "(no spaces or \\ / : * ? \" < > | characters).")
    return alias


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

    _write_binding(alias, exe)
    print(f'[OK] Win+R -> "{alias}" now opens {exe}')


def _write_binding(alias: str, exe: str) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, _subkey(alias), 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, exe)
        winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, os.path.dirname(exe))
        winreg.SetValueEx(key, MARKER, 0, winreg.REG_SZ, "1")


def cmd_unbind(args) -> None:
    alias = normalize_alias(args.alias)
    target = _read_default(winreg.HKEY_CURRENT_USER, _subkey(alias))
    if target is None:
        sys.exit(f'[!] No user-level binding for "{alias}".')
    if not _is_managed(alias) and not args.force:
        sys.exit(f'[!] "{alias}" exists but was not created by quickrun. '
                 "Use --force to delete it anyway.")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _subkey(alias))
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

    if not rows:
        print("No bindings yet. Try: quickrun bind <path\\to\\app.exe> <alias>")
        print("Or auto-detect installed apps: quickrun quickstart")
        return

    width = max(len(r[0]) for r in rows)
    for alias, target, managed in sorted(rows):
        tag = "" if managed else "  [external]"
        print(f"  {alias:<{width}}  ->  {target}{tag}")
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


PF = r"%ProgramFiles%"
PF86 = r"%ProgramFiles(x86)%"
LOCAL = r"%LocalAppData%"
ROAM = r"%AppData%"

QUICKSTART_APPS = [
    # (display name, aliases, finder)
    ("Microsoft Word",       ["word", "msword"],   _from_app_paths("winword.exe")),
    ("Microsoft Excel",      ["excel"],            _from_app_paths("excel.exe")),
    ("Microsoft PowerPoint", ["powerpoint", "ppt"], _from_app_paths("powerpnt.exe")),
    ("Microsoft Outlook",    ["outlook"],          _from_app_paths("outlook.exe")),
    ("Microsoft OneNote",    ["onenote"],          _from_app_paths("onenote.exe")),
    ("Microsoft Access",     ["access"],           _from_app_paths("msaccess.exe")),
    ("Google Chrome",        ["chrome"],
        _from_paths(rf"{PF}\Google\Chrome\Application\chrome.exe",
                    rf"{PF86}\Google\Chrome\Application\chrome.exe",
                    rf"{LOCAL}\Google\Chrome\Application\chrome.exe")),
    ("Mozilla Firefox",      ["firefox"],
        _from_paths(rf"{PF}\Mozilla Firefox\firefox.exe")),
    ("VS Code",              ["vscode"],
        _from_paths(rf"{LOCAL}\Programs\Microsoft VS Code\Code.exe",
                    rf"{PF}\Microsoft VS Code\Code.exe")),
    ("Notepad++",            ["npp"],
        _from_paths(rf"{PF}\Notepad++\notepad++.exe",
                    rf"{PF86}\Notepad++\notepad++.exe")),
    ("7-Zip",                ["7z"],
        _from_paths(rf"{PF}\7-Zip\7zFM.exe")),
    ("VLC",                  ["vlc"],
        _from_paths(rf"{PF}\VideoLAN\VLC\vlc.exe",
                    rf"{PF86}\VideoLAN\VLC\vlc.exe")),
    ("Steam",                ["steam"],
        _from_paths(rf"{PF86}\Steam\steam.exe", rf"{PF}\Steam\steam.exe")),
    ("Spotify",              ["spotify"],
        _from_paths(rf"{ROAM}\Spotify\Spotify.exe")),
    ("Telegram",             ["telegram", "tg"],
        _from_paths(rf"{ROAM}\Telegram Desktop\Telegram.exe")),
    ("WeChat",               ["wechat", "wx"],
        _from_paths(rf"{PF}\Tencent\Weixin\Weixin.exe",
                    rf"{PF}\Tencent\WeChat\WeChat.exe",
                    rf"{PF86}\Tencent\WeChat\WeChat.exe")),
    ("QQ",                   ["qq"],
        _from_paths(rf"{PF}\Tencent\QQNT\QQ.exe",
                    rf"{PF86}\Tencent\QQ\Bin\QQ.exe")),
]


def cmd_quickstart(args) -> None:
    print("Scanning for installed apps...\n")
    plan = []      # (alias, exe, display)
    skipped = []   # (alias, reason)

    for display, aliases, find in QUICKSTART_APPS:
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

    if plan:
        width = max(len(a) for a, _, _ in plan)
        print("Will bind:")
        for alias, exe, display in plan:
            print(f"  {alias:<{width}}  ->  {exe}")
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
        answer = input(f"\nBind {len(plan)} alias(es)? [Y/n] ").strip().lower()
        if answer not in ("", "y", "yes"):
            print("Cancelled.")
            return

    for alias, exe, _ in plan:
        _write_binding(alias, exe)
    print(f"\n[OK] {len(plan)} alias(es) bound. "
          "Try Win+R and type one of them.")


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
    try:
        with fetch(asset["browser_download_url"], timeout=120) as resp, \
                open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out)
    except OSError as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(f"[!] Download failed: {exc}")

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
}


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

    p_unbind = sub.add_parser("unbind", help="remove a binding")
    p_unbind.add_argument("alias")
    p_unbind.add_argument("-f", "--force", action="store_true",
                          help="also delete entries quickrun didn't create")
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
    p_qs.set_defaults(func=cmd_quickstart)

    p_update = sub.add_parser(
        "update", help="update quickrun.exe to the latest GitHub release")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
