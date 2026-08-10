# Kaggriculture — One-Time Environment Setup

Read this once at the start of a session to get the local environment
working. You shouldn't need to re-read this while actively coding the
agent — only come back to it if setup breaks, a new terminal needs
activating, or credentials expire. For game rules and how to actually
build/test/submit an agent, see `KAGGRICULTURE_REFERENCE.md`.

Local environment: macOS, VS Code, project folder at
`/Users/rohanjain/Desktop/UMD - MSML/Kaggle`, Python virtualenv at `venv/`
inside that folder.

## One-time setup (if not already done)
```bash
cd "/Users/rohanjain/Desktop/UMD - MSML/Kaggle"
python3 -m venv venv
source venv/bin/activate
pip install kaggle-environments kaggle
```

### Known quirk — pygame build failure on macOS
`pip install kaggle-environments` pulls in `pygame` (used only for
rendering, not needed for headless agent testing) which can fail to build
from source on macOS with `fatal error: 'SDL.h' file not found`. Two fixes,
try in order:
```bash
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf sdl2_gfx pkg-config
pip install kaggle-environments kaggle
```
If that doesn't resolve it, check `python3 --version` — very new Python
releases sometimes lack a prebuilt pygame wheel. Recreate the venv with
Python 3.11 or 3.12 instead:
```bash
rm -rf venv && python3.11 -m venv venv && source venv/bin/activate
pip install kaggle-environments kaggle
```

## Every new terminal session
```bash
cd "/Users/rohanjain/Desktop/UMD - MSML/Kaggle"
source venv/bin/activate
```

### Known quirk — stale PATH after installing kaggle CLI in the venv
If `which kaggle` shows a path under `/Library/Frameworks/Python.framework/...`
instead of the venv's own `.../venv/bin/kaggle`, the shell has a cached
lookup from before the venv install. Fix:
```bash
hash -r
which kaggle   # should now show .../Kaggle/venv/bin/kaggle
```

### Known quirk — Kaggle API token auth bug
The installed `kaggle` CLI version has a bug where authenticating via the
`~/.kaggle/access_token` file method throws `KeyError: 'KAGGLE_API_TOKEN'`.
Workaround: use the `export` env var method instead (this only lasts for the
current terminal session — re-run it in each new terminal, or add it to
`~/.zshrc` for persistence):
```bash
export KAGGLE_API_TOKEN=<token from https://www.kaggle.com/settings/api>
```

## Join the competition (required once, before any submission works)
Click "Join Competition" at
https://www.kaggle.com/competitions/kaggriculture, then verify from the CLI:
```bash
kaggle competitions list --group entered
```
