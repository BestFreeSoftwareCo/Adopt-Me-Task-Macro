# Adopt Me Macro (Rework v2)

A beginner-friendly macro tool for Roblox (Adopt Me) built with Python + CustomTkinter.

## Features

- Dot-based macro system (click / double / hold / key)
- Dot overlay with drag-to-position
- Record Dot mode (crosshair) to place dots by clicking on-screen
- Start/Stop + Pause/Resume global hotkeys
- Profiles (save/load)
- Post Action (beep/message/close) when the macro stops
- Single log file per run: `logs/macro.log`

## Requirements

- Windows 10/11
- Python 3.10+ recommended

## Install

1. Create and activate a virtual environment (recommended)
2. Install dependencies:

```bash
pip install -r requirements.txt
```

### AutoIt (optional, for AutoIt click backend)

If you use the AutoIt backend, you must have AutoIt installed on your PC.

## Run

### Normal

```bash
python app.py
```

### First-time friendly bootstrap

`bootstrap.py` will install missing Python packages automatically and then start the app:

```bash
python bootstrap.py
```

## Quick Start (beginner)

1. Open the app
2. Go to **Dots**
3. Click **Record Dot** and click the Roblox button you want to automate
4. Add more dots as needed
5. Press **Start / Stop** (or use your Start/Stop hotkey)

## Safety Notes

- Use the **Emergency Stop** hotkey if something goes wrong
- Prefer testing with **Test Run** before running long loops
- If "Pause on Window Change" is enabled, the macro can pause when Roblox loses focus

## Logs

- Logs are written to `logs/macro.log`
- The file is cleared each time you launch the app
- Toggle verbosity in **Advanced**:
  - Enable Logs
  - Enable Debug Mode

## Project Structure

- `app.py` - UI and app logic
- `adoptme_macro/` - core modules (runner, hotkeys, overlay, etc.)
- `profiles/` - saved profiles (local)
- `logs/` - log output (local)
- `tests/` - unit tests

## Development

Run checks:

```bash
python -m compileall -q .
python -m unittest -q
```
