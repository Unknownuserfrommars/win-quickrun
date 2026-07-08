# quickrun

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

### Option 1: standalone exe (recommended)

Grab `quickrun.exe` from [Releases](../../releases) (or build it
yourself, see below), drop it somewhere permanent, and add that
folder to your PATH. Or let the script do all of that:

```powershell
.\install.ps1
```

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
quickrun quickstart                         # auto-detect installed apps
```

### Examples

```
quickrun bind "C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE" word
quickrun -b "D:\Tools\Everything\Everything.exe" -a ev
quickrun bind "%LocalAppData%\Programs\obsidian\Obsidian.exe" notes
```

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

**Can an alias shadow a built-in name?**
Yes — HKCU wins over HKLM, so you *could* make `notepad` open
something else for your account. That's why binding over an existing
name requires `--force`.

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
