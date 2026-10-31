#!/bin/sh
# Install or update ARLOtope on macOS and Linux:
#
#   curl -fsSL https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.sh | sh
#
# Re-running updates to the newest release and keeps the previous version for rollback. Your Lab
# (your research) lives outside the app folder and is never overwritten. Optional environment:
#
#   ARLOTOPE_VERSION       release tag to install instead of the latest (e.g. v0.1.0)
#   ARLOTOPE_INSTALL_DIR   where the app lives         (Linux ~/.local/share/arlotope, macOS ~/Library/Application Support/ARLOtope)
#   ARLOTOPE_LAB_DIR       where your Lab lives        (Linux ~/ARLOtope, macOS ~/Documents/ARLOtope; remembered afterwards)
#   ARLOTOPE_BIN_DIR       where the `arlo` command goes (default ~/.local/bin)
#   ARLOTOPE_SHORTCUT_DIR  where the launcher goes     (Linux ~/.local/share/applications, macOS ~/Applications)
#   ARLOTOPE_ARCHIVE       install from this local arlotope.tar.gz instead of downloading
set -eu

REPO="AkxarLabs/ARLOtope"
START_PATH="$PATH"   # what the user's shell has, before anything below extends it

say() { printf '%s\n' "$*"; }
die() { printf 'ARLOtope install: %s\n' "$*" >&2; exit 1; }
quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }   # shell-quote one value

case "$(uname -s)" in
  Darwin) ROOT_DEFAULT="$HOME/Library/Application Support/ARLOtope"; LAB_DEFAULT="$HOME/Documents/ARLOtope"
          SHORTCUT_DEFAULT="$HOME/Applications" ;;
  Linux)  ROOT_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}/arlotope"; LAB_DEFAULT="$HOME/ARLOtope"
          SHORTCUT_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}/applications" ;;
  *) die "unsupported system $(uname -s); on Windows use install.ps1" ;;
esac
ROOT="${ARLOTOPE_INSTALL_DIR:-$ROOT_DEFAULT}"
BIN="${ARLOTOPE_BIN_DIR:-$HOME/.local/bin}"
SHORTCUTS="${ARLOTOPE_SHORTCUT_DIR:-$SHORTCUT_DEFAULT}"
if [ -n "${ARLOTOPE_LAB_DIR:-}" ]; then LAB="$ARLOTOPE_LAB_DIR"
elif [ -f "$ROOT/lab.txt" ]; then LAB="$(cat "$ROOT/lab.txt")"
else LAB="$LAB_DEFAULT"; fi
APP="$ROOT/app"

# --- uv (runs the app; installs the right Python and PyYAML on demand) ---
if ! command -v uv >/dev/null 2>&1; then
  for d in "$HOME/.local/bin" "$HOME/.cargo/bin"; do [ -x "$d/uv" ] && PATH="$d:$PATH"; done
fi
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (https://docs.astral.sh/uv/) ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || die "uv did not install; see https://docs.astral.sh/uv/getting-started/installation/"
fi
UV="$(command -v uv)"

# --- which version ---
if [ -n "${ARLOTOPE_VERSION:-}" ]; then TAG="$ARLOTOPE_VERSION"
elif [ -n "${ARLOTOPE_ARCHIVE:-}" ]; then TAG="local"
else
  TAG="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1)"
  [ -n "$TAG" ] || die "could not find the latest release of $REPO"
fi
VER="${TAG#v}"

# --- unpack into app/<version> (an existing version is reused, so pinning an old one is a rollback) ---
mkdir -p "$APP"
PREVIOUS="$(readlink "$APP/current" 2>/dev/null || true)"
if [ -d "$APP/$VER" ] && [ "$VER" != "local" ]; then
  say "ARLOtope $VER is already unpacked."
else
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  ARCHIVE="${ARLOTOPE_ARCHIVE:-}"
  if [ -z "$ARCHIVE" ]; then
    say "Downloading ARLOtope $VER ..."
    ARCHIVE="$WORK/arlotope.tar.gz"
    curl -fSL --progress-bar -o "$ARCHIVE" "https://github.com/$REPO/releases/download/$TAG/arlotope.tar.gz"
  fi
  mkdir "$WORK/unpacked"
  tar -xzf "$ARCHIVE" -C "$WORK/unpacked" --strip-components 1
  [ -f "$WORK/unpacked/arlo.py" ] || die "$ARCHIVE is not an ARLOtope release archive"
  rm -rf "$APP/$VER"
  mv "$WORK/unpacked" "$APP/$VER"
fi

# --- switch `current`, keep one previous version, drop older ones ---
ln -sfn "$VER" "$APP/current"
for d in "$APP"/*; do
  name="$(basename "$d")"
  [ -d "$d" ] && [ ! -L "$d" ] || continue
  [ "$name" = "$VER" ] || [ "$name" = "$PREVIOUS" ] || rm -rf "$d"
done

# --- the Lab: created once, outside the app, never overwritten ---
if [ -f "$LAB/lab/config.yaml" ]; then
  say "Using your existing Lab at $LAB"
else
  if [ -d "$LAB" ] && [ -n "$(ls -A "$LAB")" ]; then
    die "$LAB exists but is not an ARLOtope Lab; choose another folder with ARLOTOPE_LAB_DIR"
  fi
  say "Creating your Lab at $LAB ..."
  "$UV" run --with pyyaml python "$APP/current/tools/new_lab.py" "$LAB" --name ARLOtope >/dev/null
fi
printf '%s' "$LAB" > "$ROOT/lab.txt"

# --- the `arlo` command ---
mkdir -p "$BIN"
cat > "$BIN/arlo" <<EOF
#!/bin/sh
# ARLOtope launcher, written by install.sh. \`arlo\` opens the dashboard; \`arlo status\`, \`arlo --stop\` ... work too.
UV=$(quote "$UV")
[ -x "\$UV" ] || { PATH="\$HOME/.local/bin:\$HOME/.cargo/bin:\$PATH"; UV=uv; }
LAB=$(quote "$LAB")
case "\${1:-}" in ""|-*) set -- --hub "\$LAB" "\$@" ;; esac
ARLOTOPE_HUB="\$LAB" exec "\$UV" run --with pyyaml python $(quote "$APP/current/arlo.py") "\$@"
EOF
chmod +x "$BIN/arlo"

# --- the launcher in the applications menu ---
mkdir -p "$SHORTCUTS"
if [ "$(uname -s)" = "Darwin" ]; then
  MAC="$SHORTCUTS/ARLOtope.app/Contents"
  mkdir -p "$MAC/MacOS"
  cat > "$MAC/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>ARLOtope</string>
<key>CFBundleIdentifier</key><string>com.akxarlabs.arlotope.launcher</string>
<key>CFBundleExecutable</key><string>ARLOtope</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
EOF
  printf '#!/bin/sh\nexec %s\n' "$(quote "$BIN/arlo")" > "$MAC/MacOS/ARLOtope"
  chmod +x "$MAC/MacOS/ARLOtope"
else
  cat > "$SHORTCUTS/arlotope.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ARLOtope
Comment=Visually manage agent teams across research projects
Exec="$BIN/arlo"
Icon=$APP/current/docs/assets/brand/arlotope-mark.png
Terminal=false
Categories=Development;Science;
EOF
fi

say ""
say "ARLOtope $VER is installed."
say "  Open it:  arlo   (or the ARLOtope launcher in your applications menu)"
say "  Your Lab: $LAB"
case ":$START_PATH:" in *":$BIN:"*) ;; *) say "  Add $BIN to your PATH to use the 'arlo' command in new terminals." ;; esac
say "  Agent CLIs (Claude Code, Codex, opencode) are installed separately; see docs/install.md."
