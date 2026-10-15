#!/bin/sh
# Update WebPilot: the newest code (git pull), the extension build (extension/dist), the Python packages and, when it
# was installed with `uv tool install`, the `webpilot` command. The daemon is stopped so the next `webpilot` command
# starts the new one. Afterwards, reload the extension on the browser's extensions page.
#   ./update.sh            pull and build
#   ./update.sh --no-pull  build only (after changing the code yourself)
cd "$(dirname "$0")" || exit 1
# all of it in a function, read before it runs: the git pull below can change this very file
main() {
  pull=1
  [ "$1" = "--no-pull" ] && pull=
  for t in uv npm; do
    if ! command -v "$t" >/dev/null 2>&1; then
      echo "$t is not installed: install it (see README.md, \"Setup\"), then run ./update.sh again."
      exit 1
    fi
  done

  echo "Stopping the WebPilot daemon (it starts again on the next webpilot command) ..."
  uv run --no-sync webpilot stop >/dev/null 2>&1

  if [ -n "$pull" ]; then
    if [ ! -e .git ]; then
      echo "This folder is not a git clone, so it cannot fetch new files itself. Clone it again:"
      echo "  git clone https://github.com/thkprado/webpilot.git"
      exit 1
    fi
    if ! command -v git >/dev/null 2>&1; then
      echo "git is not installed: install it or run \"git pull\" here yourself, then run ./update.sh --no-pull."
      exit 1
    fi
    echo "Getting the newest WebPilot (git pull) ..."
    if ! git pull --ff-only; then
      echo
      echo "git pull did not succeed (the reason is above): nothing was updated. Files you changed here can stop it:"
      echo "\"git status\" lists them."
      exit 1
    fi
  fi

  echo "Building the extension ..."
  (cd extension && npm ci --no-audit --no-fund && npm run build) || { echo "The extension build failed (the reason is above)."; exit 1; }

  echo "Installing the Python packages (uv sync) ..."
  uv sync || { echo "uv sync failed (the reason is above)."; exit 1; }

  if [ ! -e extension/dist/config.json ]; then
    uv run --no-sync webpilot setup || exit 1
  fi

  if uv tool list 2>/dev/null | grep -q '^webpilot '; then
    echo "Updating the \`webpilot\` command (uv tool install) ..."
    uv tool install --editable --reinstall . || { echo "uv tool install failed (the reason is above)."; exit 1; }
  fi

  echo
  echo "WebPilot is up to date. Now reload the extension: on the browser's extensions page (chrome://extensions,"
  echo "edge://extensions, ...) click reload on the WebPilot card, in each profile that uses it."
  echo "If you installed the agent skill, \"webpilot skill list\" shows \"outdated\" when it needs \"webpilot skill install\"."
}
main "$@"
