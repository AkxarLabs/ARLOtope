# Install

One command installs ARLOtope without cloning anything. It needs an internet connection and nothing
else: it installs [uv](https://docs.astral.sh/uv/), which brings the right Python.

**Windows** (PowerShell):

```powershell
irm https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.ps1 | iex
```

**macOS and Linux**:

```bash
curl -fsSL https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.sh | sh
```

The installer downloads the latest release, creates your Lab, and adds an `arlo` command and a
launcher (Start menu on Windows, `ARLOtope.app` in `~/Applications` on macOS, the applications menu
on Linux). Open a new terminal and run `arlo`, or use the launcher; the dashboard opens in your
browser. To read the script before running it, download it from the same address and open it.

Then connect an agent and start a study: [your first study](getting-started.md#1-open-the-lab-and-connect-an-agent).
Agent CLIs (Claude Code, Codex, opencode) are **installed separately** with their own accounts; see
[platforms and agents](platforms-and-agents.md). To work from source instead, clone the repository
as shown in the README.

## Where things live

| What | Windows | macOS | Linux |
|---|---|---|---|
| App (one folder per version, `current` points at the active one) | `%LOCALAPPDATA%\ARLOtope\app\<version>` | `~/Library/Application Support/ARLOtope/app/<version>` | `~/.local/share/arlotope/app/<version>` |
| Your Lab: studies, settings, notes, records | `Documents\ARLOtope` | `~/Documents/ARLOtope` | `~/ARLOtope` |
| `arlo` command | `%LOCALAPPDATA%\ARLOtope\bin` (added to your PATH) | `~/.local/bin` | `~/.local/bin` |
| Launcher | Start menu | `~/Applications/ARLOtope.app` | `~/.local/share/applications/arlotope.desktop` |

The Lab is outside the app, so installing, updating and uninstalling never touch your research.
Back it up like any other folder (see [storage and backups](projects.md#storage-updates-and-backups)).
Server state and logs are under `~/.arlotope/`.

## Update

Stop the dashboard (Settings → About & server, or `arlo --stop`), then run the install command
again. It installs the newest release next to the old one and switches `current` to it; the previous
version is kept and older ones are removed. An existing Lab is reused and never overwritten.

## Pin a version or roll back

Set `ARLOTOPE_VERSION` to a release tag. A version that is still on disk is reused without
downloading, so this is also how you return to the previous one.

```bash
curl -fsSL https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.sh | ARLOTOPE_VERSION=v0.1.0 sh
```

```powershell
$env:ARLOTOPE_VERSION = 'v0.1.0'; irm https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.ps1 | iex
```

## Choose other locations

These environment variables are read by the installer. The Lab location is remembered for later
updates.

| Variable | Meaning |
|---|---|
| `ARLOTOPE_INSTALL_DIR` | Where the app lives |
| `ARLOTOPE_LAB_DIR` | Where a new Lab is created, or an existing one is found |
| `ARLOTOPE_BIN_DIR`, `ARLOTOPE_SHORTCUT_DIR` | Where the `arlo` command (macOS/Linux) and the launcher go (`ARLOTOPE_SHORTCUT_DIR` also applies on Windows) |
| `ARLOTOPE_NO_PATH=1` | Windows: leave your PATH alone |
| `ARLOTOPE_ARCHIVE` | Install from a local `arlotope.tar.gz` instead of downloading |

On macOS and Linux, if `~/.local/bin` is not on your PATH the installer says so; add it to your
shell profile, or use the launcher.

## Uninstall

Stop the dashboard first (`arlo --stop`). This removes the app and its launcher. It does **not**
remove your Lab, `~/.arlotope/`, uv, or any agent CLI. Delete the Lab folder yourself only if you
no longer want your research.

```powershell
# Windows
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\ARLOtope"
Remove-Item "$([Environment]::GetFolderPath('Programs'))\ARLOtope.lnk"
# also remove %LOCALAPPDATA%\ARLOtope\bin from your user PATH (System Properties → Environment Variables)
```

```bash
# macOS
rm -rf "$HOME/Library/Application Support/ARLOtope" "$HOME/Applications/ARLOtope.app" "$HOME/.local/bin/arlo"

# Linux
rm -rf "$HOME/.local/share/arlotope" "$HOME/.local/share/applications/arlotope.desktop" "$HOME/.local/bin/arlo"
```

If you chose other locations with the variables above, remove those instead.
