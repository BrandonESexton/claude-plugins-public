# mac-setup

Snapshots a Mac into a folder you keep in git, then restores it on a new Mac with one script. Run the sync again any time to bring the snapshot up to date.

**Claude Code on your Mac only.** The plugin reads your machine (Homebrew, `/Applications`, dotfiles, `defaults`). Claude Cowork and other containerized environments cannot see it, so the script refuses to run there.

## Use

- Snapshot or update: `/mac-setup:sync` (or "sync my mac setup"). It shows a diff before writing anything.
- New Mac: clone your snapshot repo, then `bash bootstrap.sh --dry-run`, then `bash bootstrap.sh`. Re-running is safe.

## What gets captured

| Item | Output | Controlled by |
| --- | --- | --- |
| Homebrew formulae, casks, taps, App Store apps, VS Code extensions | `Brewfile` | `brew bundle dump` |
| Apps installed outside Homebrew that have a cask | `Brewfile.extras` | auto-detected |
| npm globals | `npm-globals.txt` | auto |
| Dotfiles | `dotfiles/` | `dotfiles.txt` (seeded from common files that exist) |
| macOS `defaults` | `defaults.sh` | `defaults.txt` |
| App preferences (VS Code, Cursor, Ghostty, iTerm2, Rectangle, Karabiner) | `app-settings/` | `app-settings.txt` |

The setup folder's README keeps two running tables: apps that need a manual install, and configuration to do by hand.

## Configuration

Copy `config.example.yaml` to `~/.config/mac-setup/config.yaml` and set `setup_dir` (default `~/mac-setup`). The `MAC_SETUP_DIR` environment variable overrides it. If the file is missing, the skill asks and writes it.

Keep the snapshot folder in its own **private** git repo. It contains your dotfiles and app settings.

## Safety

- Files with secret-looking content are skipped with a warning. Keys, logins and licenses are never stored.
- Sync only writes inside the setup folder. Bootstrap backs up any dotfile it replaces as `.bak`.
- Bootstrap runs `brew bundle --no-upgrade` and supports `--dry-run`.

## Requirements

macOS with Homebrew, Python 3 (stdlib only), and Claude Code. `mas` is needed for App Store apps; sign in to the App Store before restoring. Some casks prompt for your password.

## Limits

Not captured: App Store/iCloud logins, SSH and GPG keys, license keys, and secrets in your environment. Bootstrap ends with a checklist for these.
