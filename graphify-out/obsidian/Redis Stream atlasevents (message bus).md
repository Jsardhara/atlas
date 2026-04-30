---
source_file: "api/main.py"
type: "code"
community: "API Config & Dependencies"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/API_Config_&_Dependencies
---

# Redis Stream: atlas:events (message bus)

## Connections
- [[API Lifespan (startupshutdown)]] - `calls` [INFERRED]
- [[TraderAgent._execute_trade]] - `calls` [EXTRACTED]
- [[TraderAgent._on_chat]] - `calls` [EXTRACTED]
- [[TraderAgent._publish_close]] - `calls` [EXTRACTED]
- [[_send_command (pauseresume agent)]] - `calls` [EXTRACTED]
- [[chat_with_agent endpoint]] - `calls` [EXTRACTED]
- [[generate_strategy (triggers Architect)]] - `calls` [EXTRACTED]
- [[manual_close_trade endpoint]] - `calls` [EXTRACTED]
- [[override_signal (manual approvereject)]] - `calls` [EXTRACTED]
- [[send_message (Master Control Terminal)]] - `calls` [EXTRACTED]
- [[stream_chat SSE endpoint]] - `calls` [EXTRACTED]
- [[terminal_feed (SSE all agent events)]] - `calls` [EXTRACTED]
- [[websocket_endpoint (ws)]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/API_Config_&_Dependencies