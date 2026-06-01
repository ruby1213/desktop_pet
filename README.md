# Desktop Pet

A animated desktop pet that lives on your screen, built with Python and PyQt6.

## Features

- Walks back and forth across the bottom of your screen
- Drag and drop with your mouse — the pet falls with gravity when released
- Right-click to open a menu with a Quit option

## Requirements

- Python 3.10+
- PyQt6

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install PyQt6
```

## Run

```bash
python main.py
```

## Controls

| Action            | Result                           |
| ----------------- | -------------------------------- |
| Left-click + drag | Pick up and move the pet         |
| Release           | Drop — pet falls with gravity    |
| Right-click       | Open context menu.               |
| Quit (menu)       | Plays death animation then exits |

## Generate exe file:

pyinstaller --onefile --windowed --icon=icon.ico --add-data "assets:assets" main.py;
