# PRD - Local TTS MCP Server

## Project Overview

- **Name:** Local TTS MCP Server
- **Version:** 0.2.0
- **Description:** A local Model Context Protocol (MCP) server providing text-to-speech capabilities using Pocket TTS.
- **Purpose:** To provide AI assistants with a privacy-focused, zero-latency, offline text-to-speech tool that can "speak" to the user.
- **UX:** MCP Server (Headless/CLI integration)

## Core Features

1.  **Pocket TTS Integration**: Uses the high-quality, lightweight Pocket TTS engine optimized for Apple Silicon.
2.  **Randomized Voices**: Automatically selects a random voice from the available catalog (`alba`, `marius`, `javert`, `jean`, `fantine`, `cosette`, `eponine`, `azelma`) to provide variety and simplify the interface.
3.  **Voice Cloning**: Support for cloning a custom voice from a reference WAV file.
4.  **Privacy-First**: All processing happens locally on the machine. No audio data is sent to the cloud.
5.  **Auto-Play & Cleanup**: Audio is played immediately on the host machine via `afplay` (macOS) and temporary files are deleted instantly. No file management is required from the LLM.
6.  **Minimal Interface**: Exposes a single `speak` tool with simplified arguments.

## Architecture

- **Language:** Python 3.10+
- **Framework:** `mcp` (FastMCP), `pocket-tts`
- **Dependency Management:** `uv`
- **Transport:** stdio (Standard Input/Output)
- **Authentication:** Hugging Face (for Voice Cloning model)

## Tools

### `speak`
Generates speech from text and plays it immediately.
- **Input:** 
  - `text` (str): The text to speak.
  - `voice_path` (str, optional): Path to a WAV file for voice cloning.
- **Configuration:**
  - `LOCAL_TTS_VOICE_PATH`: Env var to set a default voice cloning file.
- **Output:** Confirmation message (e.g., "Spoken: '...'").
- **Side Effects:** Plays audio on host speakers; deletes temporary WAV file.

## Future Goals
- Streaming audio support.
