# Install or update ARLOtope on Windows (PowerShell 5.1 or newer):
#
#   irm https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.ps1 | iex
#
# Re-running updates to the newest release and keeps the previous version for rollback. Your Lab
# (your research) lives outside the app folder and is never overwritten. Optional environment:
#
#   $env:ARLOTOPE_VERSION       release tag to install instead of the latest (e.g. v0.1.0)
#   $env:ARLOTOPE_INSTALL_DIR   where the app lives          (default %LOCALAPPDATA%\ARLOtope)
#   $env:ARLOTOPE_LAB_DIR       where your Lab lives         (default Documents\ARLOtope; remembered afterwards)
#   $env:ARLOTOPE_SHORTCUT_DIR  where the Start menu shortcut goes (default your Start menu Programs folder)
#   $env:ARLOTOPE_NO_PATH       set to 1 to leave your PATH alone
#   $env:ARLOTOPE_ARCHIVE       install from this local arlotope.tar.gz instead of downloading

function Install-ARLOtope {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $repo = 'AkxarLabs/ARLOtope'
    function Get-FullPath($path) { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($path) }   # the shim needs full paths

    $root = Get-FullPath $(if ($env:ARLOTOPE_INSTALL_DIR) { $env:ARLOTOPE_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'ARLOtope' })
    $app = Join-Path $root 'app'
    $bin = Join-Path $root 'bin'
    $shortcuts = Get-FullPath $(if ($env:ARLOTOPE_SHORTCUT_DIR) { $env:ARLOTOPE_SHORTCUT_DIR } else { [Environment]::GetFolderPath('Programs') })
    $labFile = Join-Path $root 'lab.txt'
    $lab = if ($env:ARLOTOPE_LAB_DIR) { Get-FullPath $env:ARLOTOPE_LAB_DIR }
           elseif (Test-Path $labFile) { (Get-Content $labFile -Raw).Trim() }
           else { Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ARLOtope' }

    # --- uv (runs the app; installs the right Python and PyYAML on demand) ---
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        $local = Join-Path $env:USERPROFILE '.local\bin'
        if (-not (Test-Path (Join-Path $local 'uv.exe'))) {
            Write-Host 'Installing uv (https://docs.astral.sh/uv/) ...'
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        }
        $env:Path = "$local;$env:Path"
        $uv = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uv) { throw 'uv did not install; see https://docs.astral.sh/uv/getting-started/installation/' }
    }
    $uvExe = $uv.Source

    # --- which version ---
    $tag = if ($env:ARLOTOPE_VERSION) { $env:ARLOTOPE_VERSION }
           elseif ($env:ARLOTOPE_ARCHIVE) { 'local' }
           else { (Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest").tag_name }
    if (-not $tag) { throw "could not find the latest release of $repo" }
    $ver = $tag -replace '^v', ''

    # --- unpack into app\<version> (an existing version is reused, so pinning an old one is a rollback) ---
    New-Item -ItemType Directory -Force $app | Out-Null
    $current = Join-Path $app 'current'
    $previous = if (Test-Path $current) { Split-Path -Leaf (Get-Item $current).Target } else { $null }
    $dest = Join-Path $app $ver
    if ((Test-Path $dest) -and $ver -ne 'local') {
        Write-Host "ARLOtope $ver is already unpacked."
    } else {
        $work = Join-Path ([IO.Path]::GetTempPath()) ("arlotope-" + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory $work | Out-Null
        try {
            $archive = $env:ARLOTOPE_ARCHIVE
            if (-not $archive) {
                Write-Host "Downloading ARLOtope $ver ..."
                $archive = Join-Path $work 'arlotope.tar.gz'
                Invoke-WebRequest "https://github.com/$repo/releases/download/$tag/arlotope.tar.gz" -OutFile $archive
            }
            $unpacked = Join-Path $work 'unpacked'
            New-Item -ItemType Directory $unpacked | Out-Null
            # the system tar (Windows 10+), not a GNU tar from PATH, which reads "C:" as a remote host
            & (Join-Path $env:SystemRoot 'System32\tar.exe') -xzf $archive -C $unpacked --strip-components 1
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $unpacked 'arlo.py'))) {
                throw "$archive is not an ARLOtope release archive"
            }
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            Move-Item $unpacked $dest
        } finally {
            Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
        }
    }

    # --- switch `current` (a junction: no admin rights needed), keep one previous version, drop older ones
    #     (a re-run of the same version keeps all) ---
    if (Test-Path $current) { [IO.Directory]::Delete($current) }
    New-Item -ItemType Junction -Path $current -Target $dest | Out-Null
    if ($previous -ne $ver) {
        Get-ChildItem $app -Directory | Where-Object {
            -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -and $_.Name -ne $ver -and $_.Name -ne $previous
        } | Remove-Item -Recurse -Force
    }

    # --- the Lab: created once, outside the app, never overwritten ---
    if (Test-Path (Join-Path $lab 'lab\config.yaml')) {
        Write-Host "Using your existing Lab at $lab"
    } else {
        if ((Test-Path $lab) -and (Get-ChildItem $lab -Force | Select-Object -First 1)) {
            throw "$lab exists but is not an ARLOtope Lab; choose another folder with `$env:ARLOTOPE_LAB_DIR"
        }
        Write-Host "Creating your Lab at $lab ..."
        & $uvExe run --with pyyaml python (Join-Path $current 'tools\new_lab.py') $lab --name ARLOtope | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'creating the Lab failed' }
    }
    New-Item -ItemType Directory -Force $root | Out-Null
    [IO.File]::WriteAllText($labFile, $lab)

    # --- the `arlo` command ---
    New-Item -ItemType Directory -Force $bin | Out-Null
    $shim = @"
@echo off
rem ARLOtope launcher, written by install.ps1. "arlo" opens the dashboard; "arlo status", "arlo --stop" ... work too.
set "UV=$uvExe"
if not exist "%UV%" set "UV=uv"
set "ARLOTOPE_HUB=$lab"
set "FIRST=%~1"
if "%FIRST%"=="" goto dashboard
if "%FIRST:~0,1%"=="-" goto dashboard
"%UV%" run --with pyyaml python "$current\arlo.py" %*
exit /b %errorlevel%
:dashboard
"%UV%" run --with pyyaml python "$current\arlo.py" --hub "$lab" %*
exit /b %errorlevel%
"@
    $arlo = Join-Path $bin 'arlo.cmd'
    [IO.File]::WriteAllText($arlo, ($shim -replace "`r?`n", "`r`n"), (New-Object Text.UTF8Encoding $false))

    # --- Start menu shortcut ---
    New-Item -ItemType Directory -Force $shortcuts | Out-Null
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $shortcuts 'ARLOtope.lnk'))
    $link.TargetPath = $arlo
    $link.WorkingDirectory = $lab
    $link.WindowStyle = 7   # minimized: the launcher only starts the dashboard and exits
    $link.Description = 'Visually manage agent teams across research projects'
    $link.Save()

    # --- PATH ---
    if ($env:ARLOTOPE_NO_PATH -ne '1') {
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        if (($userPath -split ';') -notcontains $bin) {
            [Environment]::SetEnvironmentVariable('Path', (($userPath, $bin | Where-Object { $_ }) -join ';'), 'User')
        }
        if (($env:Path -split ';') -notcontains $bin) { $env:Path = "$env:Path;$bin" }
    }

    Write-Host ''
    Write-Host "ARLOtope $ver is installed."
    Write-Host '  Open it:  arlo   (or ARLOtope in the Start menu)'
    Write-Host "  Your Lab: $lab"
    Write-Host '  Agent CLIs (Claude Code, Codex, opencode) are installed separately; see docs/install.md.'
}

Install-ARLOtope
