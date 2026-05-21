# Nations at War

[![Build executables](https://github.com/DCX-dev/Nations-at-War/actions/workflows/build.yml/badge.svg)](https://github.com/DCX-dev/Nations-at-War/actions/workflows/build.yml)

A **world war map simulator** inspired by *Ages of Conflict*. Watch AI nations fight over territory, or step in with god-mode tools to destroy nations and force conquests.

**Repository:** [github.com/DCX-dev/Nations-at-War](https://github.com/DCX-dev/Nations-at-War)

## Features

- **Default World Map** — Real-world country borders (177 nations from Natural Earth), equirectangular 360×180° map
- **Create Custom Map** — Paint territories, rename nations, then start the simulation
- **Autonomous warfare** — Border battles, military growth, conquest, and elimination
- **Capitals** — Red dots mark capitals; capture one to destroy that nation and free its land
- **Year counter** — Time advances from 1900 as the war runs
- **God mode** — Select a nation, click an enemy to annex them, or use **Destroy** / **Attack!**
- Speed controls (toolbar or `+` / `-`), pause with **Space**

## Download (Windows & macOS)

Pre-built executables are created automatically by [GitHub Actions](https://github.com/DCX-dev/Nations-at-War/actions/workflows/build.yml):

1. Open the **Actions** tab on the repo
2. Click the latest **Build executables** run on `main`
3. Download the artifact:
   - **NationsAtWar-Windows** — unzip, then run `NationsAtWar/NationsAtWar.exe`
   - **NationsAtWar-macOS** — unzip, then open **`NationsAtWar.app`**

> On macOS, if Gatekeeper blocks the app: right-click → **Open**, or allow it in **System Settings → Privacy & Security**.

## Requirements (run from source)

- Python 3.10–3.13 (3.14 breaks pygame fonts)
- pygame, numpy

## Run from source

**Recommended** (uses the bundled Python 3.13 venv):

```bash
cd "Nations at War"
chmod +x run.sh
./run.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

> **Python 3.14:** System `python3` on macOS may be 3.14, where pygame’s font module is currently broken. Use `./run.sh` or `.venv/bin/python main.py` instead of bare `python main.py`.

## Controls

| Action | Input |
|--------|--------|
| Paint territory (editor) | Left-click drag |
| Erase (editor) | Right-click |
| Select nation | Click on map or nation list |
| Annex enemy | Click your nation, then click enemy |
| Pause / resume | Space or toolbar |
| Speed | Toolbar or +/- keys |
| Back to menu | Esc or Menu button |
| Rename (editor) | Select nation → Rename → type → Enter |

## Build executables locally

```bash
pip install -r requirements-build.txt
pyinstaller build.spec --noconfirm
# Output: dist/NationsAtWar/  (Windows: NationsAtWar.exe, macOS: NationsAtWar.app)
```

Enjoy watching the world burn.
