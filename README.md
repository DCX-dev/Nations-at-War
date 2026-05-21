# Nations at War

A **world war map simulator** inspired by *Ages of Conflict*. Watch AI nations fight over territory, or step in with god-mode tools to destroy nations and force conquests.

## Features

- **Default World Map** — Real-world country borders (177 nations from Natural Earth), equirectangular 360×180° map
- **Create Custom Map** — Paint territories, rename nations, then start the simulation
- **Autonomous warfare** — Border battles, military growth, conquest, and elimination
- **God mode** — Select a nation, click an enemy to annex them, or use **Destroy** / **Attack!**
- Speed controls (toolbar or `+` / `-`), pause with **Space**

## Requirements

- Python 3.10+
- pygame, numpy

## Run

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

Enjoy watching the world burn.
