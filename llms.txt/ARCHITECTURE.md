# Architecture & Design

This document describes the internal architecture of the Local TTS MCP Server.

## Overview

The system is designed as a **Client-Server** application to solve the problem of multiple AI agents (e.g., Claude Desktop, VS Code, Cursor) launching separate instances of the MCP server, which would otherwise lead to excessive memory consumption if each instance loaded its own copy of the TTS model.

### Key Components

1.  **MCP Client (`server.py`)**:
    -   A lightweight process that implements the Model Context Protocol.
    -   Running instance per AI tool (e.g., one for Claude, one for VS Code).
    -   Exposes the `speak` tool to the LLM.
    -   Does **not** load PyTorch or the TTS model.
    -   Forwards requests to the background service via a Unix Domain Socket (UDS).

2.  **Inference Service (`service.py`)**:
    -   A single background daemon process (singleton).
    -   Loads the heavy **Pocket TTS** model into memory.
    -   Manages a request queue for all incoming TTS tasks.
    -   Handles audio generation and playback.
    -   Automatically shuts down or unloads the model after a period of inactivity.

3.  **Resource Manager (`resource_manager.py`)**:
    -   Runs within the Inference Service.
    -   Continuously monitors system RAM and CPU usage via `psutil`.
    -   Prevents model loading or inference if system memory is critically low.
    -   Provides status updates to clients.

4.  **System Lock (`system_lock.py`)**:
    -   Used by the service to coordinate playback serialization (though less critical now that a single service handles queuing, it ensures future extensibility).

## Data Flow

1.  **Request**: LLM calls `speak(text="Hello")`.
2.  **Client**: `server.py` receives the request.
3.  **Connection**: Client checks if `inference.sock` exists.
    -   If yes, connects to it.
    -   If no, spawns `service.py` as a detached background process and waits for the socket to appear.
4.  **Forwarding**: Client sends JSON payload `{"text": "Hello"}` to the service.
5.  **Service**:
    -   Receives request.
    -   Checks **Resource Manager** for available RAM.
    -   Loads Model (if not loaded).
    -   Generates Audio.
    -   Plays Audio via `afplay` (macOS) or `aplay` (Linux).
    -   Returns status to Client.
6.  **Response**: Client returns "Audio queued..." to the LLM.

## Directory Structure

```
src/local_tts/
├── client.py          # Lightweight client logic (connects to UDS)
├── server.py          # MCP Server entry point (uses client.py)
├── service.py         # Heavy background service (loads model)
├── resource_manager.py # System monitoring (psutil)
└── system_lock.py     # (Legacy/Shared) Coordination primitives
```

## Resource Management Strategies

-   **Lazy Loading**: The model is only loaded when the first `speak` request arrives.
-   **Auto-Unload**: The service unloads the model from GPU/RAM after 60 seconds of inactivity.
-   **Throttling**: If system RAM usage exceeds 85% (configurable), new requests are paused or rejected.
-   **Single Instance**: The service uses a fixed UDS path (`/tmp/local-tts-mcp/inference.sock`) to ensure only one instance runs.
