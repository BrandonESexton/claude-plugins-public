---
name: sync
description: >
  Use when the user wants to snapshot or update their Mac setup. Triggers on: "sync my mac setup",
  "update the brewfile", "refresh bootstrap script", "capture my current setup", "what changed
  since my last mac snapshot". Updates the setup folder from the current machine and shows a diff.
  Claude Code on the Mac only; it cannot work in Cowork or any container.
metadata:
  version: "0.2.0"
---

## Before anything

1. **Host check.** This must run in Claude Code on the user's own Mac. If you are in Cowork, a container, or any non-macOS host, stop and say so: it cannot see their machine. Do not try to emulate it.
2. **Find the setup folder.** Order: `MAC_SETUP_DIR` env var, then `setup_dir:` in `~/.config/mac-setup/config.yaml`, then `~/mac-setup`. If no config file exists, ask where to keep the snapshot (recommend its own private git repo, since it holds dotfiles and app settings), write `~/.config/mac-setup/config.yaml` from `config.example.yaml`, and continue.

## Sync

1. Run `python3 <plugin>/scripts/mac_setup.py sync --dry-run` and show the diff it prints (added/removed packages, changed dotfiles, defaults and app settings, apps installed outside Homebrew, secret warnings).
2. If a secret warning appears, stop and ask. Never copy a flagged file until the user approves or removes the line.
3. After approval, run it without `--dry-run`. Summarize what changed in a few lines. Do not commit or push unless asked.
4. To cover more, edit the lists in the setup folder, then re-run sync: `dotfiles.txt`, `defaults.txt` (macOS `domain key` pairs), `app-settings.txt` (`file:`/`dir:` under ~, or `plist:<domain>`; for apps like Raycast, Rectangle, Karabiner, find where each stores settings).
5. Apps installed outside Homebrew are checked for a cask and listed in `Brewfile.extras`. Apps with no cask go in the setup README's "Apps that need a manual install" table (sync keeps your Notes). The "Configuration to do by hand" table is never edited by sync; add a row when the user mentions a manual step (login, permission, license, setting).

## New Mac

Clone the snapshot repo and run `bash bootstrap.sh` (`--dry-run` first to preview). It is idempotent. Secrets, SSH/GPG keys, logins and licenses are never captured.
