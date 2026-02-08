# Local TTS MCP Server

<div align="center">
  <hr width="50%">
  <h3>Support This Project</h3>
  <table style="border: none; border-collapse: collapse;">
    <tr style="border: none;">
      <td align="center" style="border: none; vertical-align: middle; padding: 20px;">
        <h4>Stripe</h4>
        <img src="qr-stripe-donation.png" alt="Scan to donate" width="180"/>
        <p><a href="https://raw.githubusercontent.com/nbiish/license-for-all-works/8e9b73b269add9161dc04bbdd79f818c40fca14e/qr-stripe-donation.png">Donate via Stripe</a></p>
      </td>
      <td align="center" style="border: none; vertical-align: middle; padding: 20px;">
        <a href="https://www.buymeacoffee.com/nbiish">
          <img src="buy-me-a-coffee.svg" alt="Buy me a coffee" />
        </a>
      </td>
    </tr>
  </table>
  <hr width="50%">
</div>

Add high-quality, local text-to-speech capabilities to your AI assistant. Powered by **Pocket TTS**, this MCP server runs entirely on your machine—ensuring zero latency, zero cost, and complete privacy.

## Features

- 🚀 **Fast & Local**: Optimized for Apple Silicon. No cloud APIs, no internet required.
- 🗣️ **Natural Voices**: Uses high-quality Pocket TTS voices.
- 🔊 **Auto-Play**: Audio plays immediately on the server machine.
- 🎲 **Simple Usage**: Automatically selects a random voice for variety.
- 🦜 **Voice Cloning**: Clone any voice using a reference WAV file.
- 🔒 **Private**: All audio generation happens locally.

## Installation

### Prerequisites

- [uv](https://github.com/astral-sh/uv) (Recommended for fast setup)
- Python 3.10+
- macOS (Required for `afplay` support)
- **Hugging Face Account** (Required for Voice Cloning only)

### Voice Cloning Setup

To use the voice cloning feature, you must:

1.  Accept the terms of service for the [kyutai/pocket-tts](https://huggingface.co/kyutai/pocket-tts) model on Hugging Face.
2.  Authenticate locally using the Hugging Face CLI:
    ```bash
    uvx hf auth login
    ```

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
           "run",
           "--directory",
           "/ABSOLUTE/PATH/TO/local-tts-mcp",
           "local-tts"
         ],
         "env": {
           "LOCAL_TTS_VOICE_PATH": "/path/to/your/custom-voice.wav"
         }
       }
     }
   }
   ```
   *Note: `LOCAL_TTS_VOICE_PATH` is optional. If omitted, the server uses random default voices.*

3. **Restart Claude Desktop**.

## Available Tools

### `speak`

Generates speech from text and plays it immediately on the host machine.

- **Arguments**:
  - `text` (string): The text you want spoken.
  - `voice_path` (string, optional): Path to a WAV file for voice cloning.
- **Behavior**:
  - Uses `LOCAL_TTS_VOICE_PATH` if configured and no `voice_path` is provided.
  - Falls back to a random voice if no cloning source is available.
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

## Citation

```bibtex
@misc{local-tts-mcp2026,
  author/creator/steward = {ᓂᐲᔥ ᐙᐸᓂᒥᑮ-ᑭᓇᐙᐸᑭᓯ (Nbiish Waabanimikii-Kinawaabakizi), also known legally as JUSTIN PAUL KENWABIKISE, professionally documented as Nbiish-Justin Paul Kenwabikise, Anishinaabek Dodem (Anishinaabe Clan): Animikii (Thunder), descendant of Chief ᑭᓇᐙᐸᑭᓯ (Kinwaabakizi) of the Beaver Island Band and enrolled member of the sovereign Grand Traverse Band of Ottawa and Chippewa Indians},
  title/description = {local-tts-mcp},
  type_of_work = {Indigenous digital creation/software incorporating traditional knowledge and cultural expressions},
  year = {2026},
  publisher/source/event = {GitHub repository under tribal sovereignty protections},
  howpublished = {\url{https://github.com/nbiish/local-tts-mcp}},
  note = {Authored and stewarded by ᓂᐲᔥ ᐙᐸᓂᒥᑮ-ᑭᓇᐙᐸᑭᓯ (Nbiish Waabanimikii-Kinawaabakizi), also known legally as JUSTIN PAUL KENWABIKISE, professionally documented as Nbiish-Justin Paul Kenwabikise, Anishinaabek Dodem (Anishinaabe Clan): Animikii (Thunder), descendant of Chief ᑭᓇᐙᐸᑭᓯ (Kinwaabakizi) of the Beaver Island Band and enrolled member of the sovereign Grand Traverse Band of Ottawa and Chippewa Indians. This work embodies Indigenous intellectual property, traditional knowledge systems (TK), traditional cultural expressions (TCEs), and associated data protected under tribal law, federal Indian law, treaty rights, Indigenous Data Sovereignty principles, and international indigenous rights frameworks including UNDRIP. All usage, benefit-sharing, and data governance are governed by the COMPREHENSIVE RESTRICTED USE LICENSE FOR INDIGENOUS CREATIONS WITH TRIBAL SOVEREIGNTY, DATA SOVEREIGNTY, AND WEALTH RECLAMATION PROTECTIONS.}
}
```

Copyright © 2026 ᓂᐲᔥ ᐙᐸᓂᒥᑮ-ᑭᓇᐙᐸᑭᓯ (Nbiish Waabanimikii-Kinawaabakizi), also known legally as JUSTIN PAUL KENWABIKISE, professionally documented as Nbiish-Justin Paul Kenwabikise, Anishinaabek Dodem (Anishinaabe Clan): Animikii (Thunder), a descendant of Chief ᑭᓇᐙᐸᑭᓯ (Kinwaabakizi) of the Beaver Island Band, and an enrolled member of the sovereign Grand Traverse Band of Ottawa and Chippewa Indians. This work embodies Traditional Knowledge and Traditional Cultural Expressions. All rights reserved.
