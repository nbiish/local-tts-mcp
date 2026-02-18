# TODO

## In Progress

- [ ] Add streaming audio support (future)

## Completed

- [x] Initial setup of MCP server structure
- [x] Integration with Pocket TTS engine
- [x] Implement `speak` tool
- [x] Optimize for Apple Silicon
- [x] Simplify `speak` tool interface (remove engine/voice selection)
- [x] Implement random voice selection
- [x] Remove `list_engines` tool to minimize token usage
- [x] Update documentation and installation guide (uv support)
- [x] Implement Voice Cloning support (`voice_path` argument)
- [x] Implement Default Voice Cloning via `LOCAL_TTS_VOICE_PATH`
- [x] Add Authentication support for gated models (Hugging Face)
- [x] Implement background system status monitoring and memory management
- [x] Refactor to Client-Server architecture (Single Model Instance)
