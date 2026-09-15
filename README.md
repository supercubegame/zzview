# zzview - Hacker News Browser

A lightweight, cross-platform desktop application to browse Hacker News stories, comments, and user submissions.

## Features

- **Top Stories**: View the latest trending stories on Hacker News
- **Newest**: Check the most recently submitted posts
- **Click to Open**: Click any story title to open it in your default browser
- **Cross-platform**: Runs on Linux, macOS, and Windows
- **No dependencies**: Standalone binaries, no installation required

## Building

```bash
rustc --version  # Requires Rust 1.70+
cargo build --release
./target/release/zzview
```

## Architecture

- **GUI**: iced 0.12 (native UI toolkit)
- **HTTP**: reqwest for fetching from news.ycombinator.com/api/
- **Runtime**: tokio for async I/O
- **Data**: serde_json for parsing API responses

## Downloads

Prebuilt binaries are available in [Releases](https://github.com/supercubegame/zzview/releases).
