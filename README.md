# Local TTS MCP Server

Add high-quality, local text-to-speech capabilities to your AI assistant. Powered by **Pocket TTS**, this MCP server runs entirely on your machine—ensuring zero latency, zero cost, and complete privacy.

## Features

- 🚀 **Fast & Local**: Optimized for Apple Silicon. No cloud APIs, no internet required.
- 🗣️ **Natural Voices**: Uses high-quality Pocket TTS voices.
- 🔊 **Auto-Play**: Audio plays immediately on the server machine.
- 🎲 **Simple Usage**: Automatically selects a random voice for variety.
- 🔒 **Private**: All audio generation happens locally.

## Installation

### Prerequisites

- [uv](https://github.com/astral-sh/uv) (Recommended for fast setup)
- Python 3.10+
- macOS (Required for `afplay` support)

### Quick Start (Claude Desktop)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/local-tts-mcp.git
   cd local-tts-mcp
   ```

2. **Add to Claude Desktop Config**:
   
   Open your config file:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   
   Add the following entry to `mcpServers`. Make sure to replace `/ABSOLUTE/PATH/TO/...` with the actual path to where you cloned the repo.

   ```json
   {
     "mcpServers": {
       "local-tts": {
         "command": "uv",
         "args": [
           "--directory",
           "/ABSOLUTE/PATH/TO/local-tts-mcp",
           "run",
           "local-tts"
         ]
       }
     }
   }
   ```

3. **Restart Claude Desktop**.

## Available Tools

### `speak`

Generates speech from text and plays it immediately on the host machine.

- **Arguments**:
  - `text` (string): The text you want spoken.
- **Behavior**:
  - Selects a random voice.
  - Plays audio locally.
  - Automatically cleans up temporary files.

## Development

To run the server locally for testing:

```bash
# Install dependencies and run
uv run local-tts
```

## License

MIT
