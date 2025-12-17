# Changelog

This file documents notable changes in a community-friendly way.

## How to read this changelog

- **[Unreleased]** = changes that are in the repo but not part of a named release yet.
- Sections are grouped by **Added**, **Changed**, **Fixed**, and **Security**.
- If you’re troubleshooting, check the **Logging & Troubleshooting** section below.

## [Unreleased]

### Highlights

- App access now includes a **Terms of Service step** and a **Discord access key step**.
- Global hotkeys have improved validation/normalization (more reliable on different formats).
- Macro runner is more resilient (better behavior if the background thread hits an error).
- Profile operations are safer (corrupted profile files won’t hard-crash the UI).

### Added

- **Access key gate after Terms of Service acceptance**.
  - After accepting the ToS, you’ll be prompted to **join the Discord server** (button opens an invite link) and **paste an access key**.
  - The access key is intentionally **not displayed** in the app UI.
- **Persistent access state** via the `access_key_accepted` setting.
  - Once accepted, you won’t be prompted again on future launches (unless your `config.json` is removed/reset).
- **Startup gating** for safety.
  - Main macro controls are disabled and global hotkeys are deferred until ToS + access key are completed.
- **Community-friendly UI messaging** around gate status.
  - If you press a hotkey before completing the gate, the app shows a short message explaining what to do.

### Changed

- **Hotkey behavior respects the startup gate**.
  - Hotkeys won’t start until the gate is passed.
  - If something triggers a hotkey callback early, the action is blocked and a message is shown.
- **Profile loading preserves global gate flags**.
  - Loading a profile will not overwrite:
    - `tos_accepted_version`
    - `discord_prompt_shown`
    - `access_key_accepted`

### Fixed

- **Hotkey normalization** to avoid invalid/duplicated wrapping (example: `<<f6>>`).
  - Hotkeys entered as `f6`, `<f6>`, or combos like `ctrl+shift+s` are normalized to a consistent internal format.
  - Start/Stop and Pause/Resume are required to be **different** hotkeys.
- **Macro runner stability** improvements.
  - If the background runner thread encounters an unexpected exception, it is now:
    - logged (when logging is enabled)
    - stopped cleanly so UI state doesn’t get stuck
  - `stop()` is now **idempotent** (won’t double-fire “stopped” callbacks if you stop twice).
- **Profile operations are crash-safe**.
  - Save/Load/Delete profile actions now show a message on failure instead of crashing the app.
  - Profile hotkeys are validated on load; invalid profile hotkeys won’t break your current hotkeys.

### Hotkeys (User Guide)

- **Start/Stop (default)**
  - `F6`
- **Pause/Resume (default)**
  - `F7`
- **Emergency Stop (default)**
  - `Ctrl + Shift + S`

Notes:

- Hotkeys may not work if the app doesn’t have permission to receive global key events on your system.
- If hotkeys don’t trigger, you can still use the on-screen buttons.

### Logging & Troubleshooting

- **Log file location**
  - `logs/macro.log`
- **What to look for**
  - Hotkey presses should generate log entries.
  - Runner errors will be logged as a crash/exception (when logging is enabled).

Quick checks:

- If hotkeys do nothing, confirm you’ve completed the ToS + access key gate.
- Try pressing `F6` / `F7` and look for:
  - a short UI message, and
  - new lines appended to `logs/macro.log`

### Files & Folders

- **`config.json`**
  - Your main settings and dot list.
- **`profiles/`**
  - Saved profiles as JSON files.
- **`logs/`**
  - Contains `macro.log`.

### Security

- Access key validation is performed via **SHA-256 hash comparison**.
  - The plaintext key is not shown in the UI.
  - This changelog intentionally does not include the plaintext key.
