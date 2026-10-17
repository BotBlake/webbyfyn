# Webbyfyn

Webbyfyn is a proof-of-concept desktop client for [Jellyfin](https://jellyfin.org/), written in Python. It embeds Jellyfin's web UI in a Qt WebEngine window and handles video playback through an embedded [mpv](https://mpv.io/) player. The goal is to preserve the familiar Jellyfin interface while taking advantage of mpv's enhanced playback capabilities.

## Run the PoC

Install Python 3.12 or later, the project's Python dependencies, and a compatible system version of `libmpv`, then run:

```sh
uv run main.py --server https://your-jellyfin-server
```

## Before the First Release

Webbyfyn is still far from being a finished client. The following tasks need to be completed before the first stable release:

- [ ] Package and distribute standalone Linux and Windows applications, including Qt WebEngine, libmpv, icons, metadata, and an update mechanism
- [ ] Create accurate Jellyfin device profiles, including codec, container, subtitle, and transcoding capabilities
- [ ] Add unit, integration, UI, compatibility, performance, and stability tests
- [ ] Implement server discovery, selection, editing, and connection error handling instead of requiring `--server`
- [ ] Store session tokens securely, support logout and token revocation, and allow multiple user accounts and profiles
- [ ] Add settings and launch options for TV mode, fullscreen startup, and controller- or keyboard-first navigation
