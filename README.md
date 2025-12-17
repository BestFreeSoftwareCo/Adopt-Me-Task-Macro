# Adopt Me Macro (Rework v2)

A beginner-friendly macro tool for Roblox (Adopt Me) built with Python + CustomTkinter.

<div align="center">

![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-CustomTkinter-111827)
![Hotkeys](https://img.shields.io/badge/hotkeys-pynput-4B5563)

</div>

**Quick links**

- [Getting Started](#getting-started)
- [Hotkeys](#hotkeys)
- [Logging & Troubleshooting](#logging--troubleshooting)
- [Community / Discord](#community--discord)
- [Changelog](CHANGELOG.md)

> [!IMPORTANT]
> This project is not affiliated with Roblox. Use responsibly and at your own risk.

## Overview

Adopt Me Macro (Rework v2) is a dot-based macro runner designed for a simple workflow:

- Create or record dots on the screen
- Preview or run the loop
- Control the macro using global hotkeys or the UI
- Save/load profiles locally

## Key Features

- **Dot-based macros**
  - Click / double click / hold click / key press per dot
- **On-screen overlay**
  - Drag dots to position with an always-on-top overlay
  - Optional dot numbers and coordinates
- **Record Dot mode**
  - Crosshair overlay to capture a screen position by clicking
- **Global hotkeys**
  - Start/Stop and Pause/Resume
  - Emergency stop
- **Safety and QoL**
  - Pause when Roblox loses focus (optional)
  - Test Run mode for quick validation
  - Post-action (beep/message/close) after the macro stops
- **Profiles + local storage**
  - Save/load profiles to `profiles/`
  - Settings and dots stored in `config.json`
- **Logs**
  - Per-run log output written to `logs/macro.log`

## Getting Started

### Requirements

- **Operating system**
  - Windows 10/11
- **Python**
  - Python 3.10+ recommended

### Install

1. Create and activate a virtual environment (recommended)
2. Install dependencies:

```bash
pip install -r requirements.txt
```

### AutoIt backend (optional)

If you want to use the AutoIt click backend, install AutoIt on your PC first.
You can switch the click backend inside the app.

### Run

**Option A: Normal**

```bash
python app.py
```

**Option B: First-time friendly bootstrap**

`bootstrap.py` can install missing Python packages automatically and then start the app:

```bash
python bootstrap.py
```

## First Launch (ToS + Access Key)

On first launch (or after resetting `config.json`), the app will:

1. Show the Terms of Service
2. Prompt you to join the Discord server and enter an access key

Notes:

- The access key is not displayed in the UI.
- The key is provided via the Discord community.

## Usage

### Quick Start

1. Open the app
2. Go to **Dots**
3. Click **Record Dot** and click the Roblox button you want to automate
4. Add more dots as needed
5. Use **Test Run** to preview
6. Press **Start / Stop** (or use your Start/Stop hotkey)

### Dots & Overlay

- Drag overlay dots to fine-tune positions
- While the macro is running:
  - The overlay hides automatically
  - It returns when the macro stops

### Record Dot mode

- Click **Record Dot**
- Click the target location on your screen
- Press `Esc` to cancel

### Profiles

Profiles let you quickly switch between different dot sets and settings.

- **Save**
  - Enter a profile name and save
- **Load**
  - Select a profile to load it
- **Safety**
  - Corrupted profiles won’t crash the app
  - Gate acceptance (ToS/access) is preserved across profile loads

## Hotkeys

Defaults:

- **Start/Stop**
  - `F6`
- **Pause/Resume**
  - `F7`
- **Emergency Stop**
  - `Ctrl + Shift + S`

Hotkey notes:

- Hotkeys only start after the ToS + access gate is completed.
- Some systems require running the app with elevated privileges for global hotkeys to work reliably.
- If hotkeys don’t trigger, you can still use the on-screen buttons.

## Logging & Troubleshooting

### Logs

- **Location**
  - `logs/macro.log`
- **Behavior**
  - The log file is cleared on each launch
  - Enable more details via the **Advanced** tab:
    - Enable Logs
    - Enable Debug Mode

### Common issues

- **Hotkeys don’t work**
  - Confirm you’ve completed the ToS + access key prompts
  - Check `logs/macro.log` for hotkey startup errors
  - Try running as Administrator
  - Ensure no other app is capturing the same hotkeys
- **Clicks don’t register / feel inconsistent**
  - Try switching click backend (AutoIt vs Win32)
  - Confirm Roblox is in the foreground if focus checks are enabled
- **Runner stops unexpectedly**
  - Check `logs/macro.log` for an exception (runner crashes are logged when logging is enabled)

## Community / Discord

- **Discord invite**
  - https://discord.com/invite/498tyUUaBw

When reporting an issue, include:

- Windows version (10/11)
- Python version
- Click backend (AutoIt or Win32)
- A snippet of `logs/macro.log`

## Project Structure

- **`app.py`**
  - UI and app logic
- **`adoptme_macro/`**
  - Core modules (runner, hotkeys, overlay, storage, etc.)
- **`profiles/`**
  - Saved profiles (local)
- **`logs/`**
  - Log output (local)
- **`tests/`**
  - Unit tests

## Development

Run checks:

```bash
python -m compileall -q .
python -m unittest -q
```

## Security & Privacy

- Access keys are validated via a SHA-256 hash comparison.
- Config, profiles, and logs are stored locally in this repo folder.

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md).

## License

This repository currently does not include a `LICENSE` file.
If you intend to redistribute or modify this project, clarify licensing with the repository owner.

## Disclaimer

This project is provided as-is, with no warranty.
Use responsibly and at your own risk.
