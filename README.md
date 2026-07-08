# quickrun

[简体中文](README_zh_CN.md)

**Bind custom Win+R aliases to any Windows program.**

Windows lets you launch `notepad` or `powershell` straight from
Win+R, but not third-party apps — typing `word` does nothing, even
though `winword` mysteriously works. quickrun fixes that:

```
quickrun -b "C:\...\WINWORD.EXE" -a word
```

Then **Win+R → `word` → Enter**. That's it.

- **No admin rights** — everything lives in your user registry hive
- **Instant** — no restart, no logoff, works the moment you bind
- **Permanent** — survives reboots; stays until you `unbind`
- **Safe** — quickrun tags its own entries and never deletes
  bindings created by app installers
- Aliases also work in the **Explorer address bar**

## Install

### Option 1: one-liner (recommended)

Paste into any PowerShell window:

```powershell
irm https://raw.githubusercontent.com/Unknownuserfrommars/quickrun/main/install.ps1 | iex
```

This downloads the latest release exe to
`%LocalAppData%\Programs\quickrun` and adds it to your PATH — no
admin prompt, and `quickrun update` can later update itself in place.

Prefer a machine-wide install in `C:\Program Files`? Run from an
elevated shell in a clone of the repo:

```powershell
.\install.ps1 -SystemWide
```

(Not the default because Program Files needs admin rights for every
future self-update.) You can also just grab `quickrun.exe` from
[Releases](../../releases) and manage it yourself, yt-dlp style.

### Option 2: pip

```
pip install -e .
```

This gives you a `quickrun` command via Python's Scripts directory.

### Option 3: no install

```
python quickrun.py <command> ...
```

## Usage

```
quickrun bind <path\to\app.exe> <alias>     # bind an alias
quickrun -b <path\to\app.exe> -a <alias>    # same thing, flag style
quickrun list                               # show your bindings
quickrun unbind <alias>                     # remove one
quickrun find <name>                        # search the PC for an exe, offer to bind
quickrun quickstart                         # auto-detect installed apps
quickrun update                             # self-update from GitHub (also: -U)
quickrun --version                          # print version
```

### Examples

```
quickrun bind "C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE" word
quickrun -b "D:\Tools\Everything\Everything.exe" -a ev
quickrun bind "%LocalAppData%\Programs\obsidian\Obsidian.exe" notes
```

### Find: locate an exe you don't know the path of

```
> quickrun find obsidian
Searching for "obsidian" ...
1 result(s) in 1.2s

  Found: C:\Users\you\AppData\Local\Programs\obsidian\Obsidian.exe
Alias to bind it to (press Enter to skip): notes
[OK] Win+R -> "notes" now opens C:\Users\you\...\Obsidian.exe
```

`find` checks the registry (App Paths + installer records) first,
then scans the usual install folders with a depth limit and a hard
~10s time budget — typically it answers in 1-3 seconds. Multiple
matches show a numbered list to pick from; pressing Enter at any
prompt skips without binding.

### Quickstart: auto-detect installed apps

```
quickrun quickstart            # scan, show the plan, ask before writing
quickrun quickstart --dry-run  # only show what would be bound
quickrun quickstart --yes      # bind everything without asking
```

Quickstart detects common apps and proposes friendly aliases:

| App | Aliases |
|---|---|
| Word / Excel / PowerPoint / Outlook / OneNote / Access | `word` `msword` / `excel` / `powerpoint` `ppt` / `outlook` / `onenote` / `access` |
| Chrome / Firefox | `chrome` / `firefox` |
| VS Code / Notepad++ | `vscode` / `npp` |
| 7-Zip / VLC | `7z` / `vlc` |
| Steam / Spotify | `steam` / `spotify` |
| Telegram / WeChat / QQ | `telegram` `tg` / `wechat` `wx` / `qq` |

Names that already mean something on your system (e.g. `excel` if
Office registered it machine-wide) are skipped, never overwritten —
unless you pass `--force`.

## Command reference

| Command | Aliases | Options |
|---|---|---|
| `bind <exe> <alias>` | `b`, `-b`, `-bind` | `-a/--alias` (flag-style alias), `-f/--force` overwrite existing |
| `unbind <alias>` | `u`, `-u`, `-unbind` | `-f/--force` also remove entries quickrun didn't create |
| `list` | `l`, `ls`, `-l`, `-list` | `--all` include installer-created user entries |
| `quickstart` | `qs`, `-q`, `-quickstart` | `-y/--yes`, `-n/--dry-run`, `-f/--force` |
| `find <name>` | `f`, `-find`, `--find` | interactive; Enter skips |
| `update` | `up`, `-U`, `--update` | (standalone exe only) |
| `--version` | `-V` | |

Alias rules: case-insensitive, no spaces, no `\ / : * ? " < > |`.
A trailing `.exe` is stripped automatically.

## How it works

When you type a name into Win+R, Windows checks the **App Paths**
registry key before (and in addition to) the PATH:

```
HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\<alias>.exe
```

That's exactly how `winword` works — Office registers `winword.exe`
there under HKLM at install time. quickrun writes the same kind of
entry under **HKCU** (your user hive), which is why it needs no
admin rights and applies instantly. Each entry quickrun creates gets
a `QuickRunManaged` marker value so `unbind` and `list` can tell its
own bindings apart from ones installers made.

## FAQ

**Are bindings permanent?**
Yes. They're registry values — they survive reboots and stay until
you `unbind` them. The one thing that can break an alias is the
target app moving or being uninstalled; just rebind if that happens.

**Do I need admin rights?** No. Everything is per-user (HKCU).

**Does launching go through cmd.exe? I saw a console flash.**
No — Win+R resolves the alias and starts the target exe directly;
no shell is involved. GUI apps open with no console at all. A brief
console window only appears if the alias points at a *console*
program (that window **is** the program), or if you launch
`quickrun` itself from Win+R (it's a CLI tool; it now keeps its
window open so the help is readable).

**Can an alias shadow a built-in name?**
Yes — HKCU wins over HKLM, so you *could* make `notepad` open
something else for your account. That's why binding over an existing
name requires `--force`.

**How do I update?**
`quickrun update` (or `quickrun -U`) checks the latest GitHub
release and replaces the exe in place. If you installed via pip,
use `git pull` + `pip install -e .` instead.

**How do I remove everything?**
`quickrun list` to see your bindings, then `quickrun unbind <alias>`
for each. quickrun stores nothing anywhere else.

## Building the exe

```powershell
pip install pyinstaller
pyinstaller --onefile --name quickrun --console quickrun.py
```

The result is `dist\quickrun.exe` — a single self-contained file,
yt-dlp style. `install.ps1` does the build (if needed), copies the
exe to `%LocalAppData%\Programs\quickrun`, and adds it to your PATH.

## License

MIT
