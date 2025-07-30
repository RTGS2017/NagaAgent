# Qwen Codebase Documentation

## Overview

The Qwen project (NagaAgent) is an intelligent conversation assistant that supports multiple MCP services, streaming voice interaction, GRAG knowledge graph memory system, RESTful API interface, and an extremely streamlined code style.

## Key Features

1. **Unified Configuration Management**: All global variables, paths, and keys are managed in `config.py`, supporting .env and environment variables.
2. **RESTful API Interface**: Automatic HTTP server startup with complete conversation functionality and streaming output.
3. **GRAG Knowledge Graph Memory System**: Neo4j-based triplet knowledge graph that automatically extracts entities and relationships from conversations.
4. **HANDOFF Tool Calling Loop**: Automatic parsing and execution of tool calls returned by LLM, supporting multi-round recursive calls.
5. **Multi-Agent Capabilities**: Browser, file, code, and other agents are plug-and-play, all callable through the tool calling loop mechanism.
6. **Cross-Platform Compatibility**: Automatic adaptation for Windows/Mac, automatic browser path detection, and intelligent dependency installation.
7. **Streaming Voice Interaction**: Edge-TTS based OpenAI-compatible voice synthesis with pygame background playback and intelligent sentence splitting.
8. **Minimalist Code**: Fully commented in Chinese with decoupled components for easy expansion.
9. **PyQt5 UI**: With PNG sequence frames and fast loading animations.

## Directory Structure

```
NagaAgent/
├── main.py                     # Main entry point
├── config.py                   # Global configuration
├── conversation_core.py        # Conversation core (including main tool calling loop logic)
├── apiserver/                  # API server module
│   ├── api_server.py           # FastAPI server
│   ├── start_server.py         # Startup script
│   └── README.md               # API documentation
├── mcpserver/                  # MCP server module
│   ├── mcp_manager.py          # MCP service management
│   ├── mcp_registry.py         # Agent registration and schema metadata
│   ├── agent_manager.py        # Agent manager (independent system)
│   ├── agent_xxx/              # Custom agents (file, coder, browser, etc.)
│   │   └── agent-manifest.json # Agent configuration file
├── summer_memory/              # GRAG knowledge graph memory system
│   ├── memory_manager.py       # Memory manager
│   ├── extractor_ds_tri.py     # Triplet extractor
│   ├── graph.py                # Neo4j graph operations
│   ├── rag_query_tri.py        # Memory query
│   ├── visualize.py            # Graph visualization
│   ├── main.py                 # Standalone entry point
│   └── triples.json            # Triplet cache
├── thinking/                   # Thinking engine module
│   ├── tree_thinking.py        # Tree thinking engine
│   ├── difficulty_judge.py     # Difficulty judgment
│   └── quick_model_manager.py  # Quick model manager
├── ui/                         # Frontend UI
│   ├── pyqt_chat_window.py     # PyQt chat window
│   └── response_utils.py       # Frontend response parsing utilities
├── voice/                      # Voice related modules
├── requirements.txt            # Project dependencies
├── pyproject.toml              # Project configuration and dependencies
├── setup.ps1                   # Windows setup script
├── setup_mac.sh                # Mac setup script
├── quick_deploy_mac.sh         # Mac one-click deployment script
├── check_env.py                # Cross-platform environment check
└── README.md                   # Project documentation
```

## Configuration System

The configuration system is based on Pydantic for type safety and validation. Key configuration files include:

1. `config.py`: Main configuration class using Pydantic models
2. `config.json`: JSON configuration file that can be modified by users

### Key Configuration Sections

- **SystemConfig**: Basic system settings (version, directories, logging)
- **APIConfig**: LLM API configuration (key, base URL, model, temperature, etc.)
- **APIServerConfig**: API server settings (host, port, auto-start)
- **GRAGConfig**: Knowledge graph memory system settings
- **HandoffConfig**: Tool calling loop configuration
- **MCPConfig**: MCP service configuration
- **BrowserConfig**: Browser path and Playwright settings
- **TTSConfig**: Text-to-speech service configuration
- **UIConfig**: User interface settings
- **SystemPrompts**: System prompt templates

## Core Components

### 1. Conversation Core (`conversation_core.py`)

The main conversation processing logic with:
- LLM interaction via OpenAI API
- Tool calling loop implementation
- Integration with MCP services
- GRAG memory system integration
- Voice processing integration

### 2. MCP Server (`mcpserver/`)

Manages all MCP (Multi-Client Protocol) services:
- **MCP Manager**: Core service management
- **Agent Manager**: Independent agent registration and calling system
- **Agent Registry**: Centralized agent registration and schema metadata
- Custom agents for specific functionalities (browser, file, code, etc.)

### 3. GRAG Memory System (`summer_memory/`)

Neo4j-based knowledge graph memory system:
- Memory manager for storing and retrieving conversation memories
- Triplet extractor for entity-relation extraction
- Graph operations for Neo4j interaction
- Memory query system for relevant information retrieval
- Visualization capabilities

### 4. Thinking Engine (`thinking/`)

Advanced reasoning capabilities:
- Tree thinking engine for complex problem solving
- Difficulty judgment for question complexity assessment
- Quick model manager for rapid response scenarios

### 5. API Server (`apiserver/`)

RESTful API implementation using FastAPI:
- Chat endpoints (both regular and streaming)
- System management endpoints
- Memory statistics and information retrieval

### 6. UI (`ui/`)

PyQt5-based user interface:
- Chat window with markdown support
- Response parsing utilities
- Animation and visual enhancements

### 7. Voice System (`voice/`)

Streaming voice interaction:
- Text-to-speech using Edge-TTS
- Voice integration with the conversation system
- Audio playback handling

## Tool Calling Loop Mechanism

NagaAgent supports two types of tool calls:
1. **MCP Services**: Called with `agentType: mcp`
2. **Agent Services**: Called with `agentType: agent`

The tool calling format follows a strict JSON structure:

```json
{
  "agentType": "mcp",
  "service_name": "MCP service name",
  "tool_name": "Tool name",
  "parameter_name": "parameter_value"
}
```

Or for agent services:

```json
{
  "agentType": "agent",
  "agent_name": "Agent name",
  "prompt": "Task content"
}
```

## Agent System

All agents are registered in `mcpserver/mcp_registry.py` for centralized management. The system supports:
- Browser, file, code, and other agents
- Plug-and-play capabilities with hot-swapping
- Dynamic service pool querying

### Agent Manifest Standardization

All agents use a standardized `agent-manifest.json` configuration file ensuring consistency and maintainability.

## RESTful API

The built-in RESTful API server supports:
- Health checks
- Chat interfaces (regular and streaming)
- System management
- Memory statistics
- OpenAI-compatible endpoints

API endpoints include:
- `POST /chat` - Regular chat
- `POST /chat/stream` - Streaming chat
- `GET /system/info` - System information
- `GET /memory/stats` - Memory statistics
- `GET /v1/models` - List available models (OpenAI-compatible)
- `POST /v1/chat/completions` - Chat completions (OpenAI-compatible)

The API now supports both the original custom endpoints and OpenAI-compatible endpoints, 
allowing for better integration with existing tools and libraries.

## Setup and Deployment

### Windows
```powershell
.\setup.ps1
.\start.bat
```

### Mac
```bash
chmod +x quick_deploy_mac.sh
./quick_deploy_mac.sh
./start_mac.sh
```

The setup process automatically:
1. Creates a virtual environment
2. Installs dependencies
3. Configures LLM with DeepSeekV3 recommendation
4. Initializes the GRAG knowledge graph memory system

## Development Guidelines

1. All backend responses are structured JSON, automatically adapted by `ui/response_utils.py`
2. Frontend handles all `\n` and `\\n` newline characters properly
3. UI animations, themes, nicknames, and transparency can be customized in `config.py` and `pyqt_chat_window.py`
4. Memory weights, forgetting thresholds, and redundancy removal are all managed in `config.py`

## License

MIT License