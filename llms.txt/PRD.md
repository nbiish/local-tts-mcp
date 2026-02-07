# PRD - Local TTS MCP Server

## Project Overview

- **Name:** Local TTS MCP Server
- **Version:** 0.1.0
- **Description:** A local Model Context Protocol (MCP) server providing text-to-speech capabilities using Pocket TTS.
- **Purpose:** To provide AI assistants with a privacy-focused, zero-latency, offline text-to-speech tool that can "speak" to the user.
- **UX:** MCP Server (Headless/CLI integration)

## Core Features

1.  **Pocket TTS Integration**: Uses the high-quality, lightweight Pocket TTS engine optimized for Apple Silicon.
2.  **Randomized Voices**: Automatically selects a random voice from the available catalog (`alba`, `marius`, `javert`, `jean`, `fantine`, `cosette`, `eponine`, `azelma`) to provide variety and simplify the interface.
3.  **Privacy-First**: All processing happens locally on the machine. No audio data is sent to the cloud.
4.  **Auto-Play & Cleanup**: Audio is played immediately on the host machine via `afplay` (macOS) and temporary files are deleted instantly. No file management is required from the LLM.
5.  **Minimal Interface**: Exposes a single `speak` tool with only a `text` argument to minimize token usage.

## Architecture

- **Language:** Python 3.10+
- **Framework:** `mcp` (FastMCP), `pocket-tts`
- **Dependency Management:** `uv`
- **Transport:** stdio (Standard Input/Output)

## Tools

### `speak`
Generates speech from text and plays it immediately.
- **Input:** `text` (str)
- **Output:** Confirmation message (e.g., "Spoken: '...'").
- **Side Effects:** Plays audio on host speakers; deletes temporary WAV file.

## Future Goals
- Support for more TTS engines if needed (currently simplified to just Pocket TTS).
- Streaming audio support.
