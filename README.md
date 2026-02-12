# MicroHack: Agentic AI Memory

Welcome to the Agentic AI Memory MicroHack!
This hands-on workshop explores various types of memory architectures in agent and multi-agent systems. You'll learn how agents use different memory layers to enable smarter, context-aware interactions and persistent knowledge.

## Workshop Overview

This MicroHack guides you through the fundamentals and advanced concepts of agentic memory, from short-term session storage to long-term semantic search and knowledge base integration. You'll work with a base UI and agent backend, implementing memory features, exposing data via agent tools (read/write), and connecting to databases. A key theme is turning raw conversation data into useful long-term signals via batch processing (titles, summaries, embeddings, metadata) that can be safely searched and reused.

### Learning Objectives
- Understand different memory types in agentic systems
- Implement short-term, mid-term, and long-term memory using modern databases
- Design memory access patterns via agent tools (read/write) and prompt injection
- Build batch processing pipelines over raw conversation data (naming, summaries, embeddings, metadata)
- Explore user memory, knowledge base, and multi-agent scratchpad concepts
- Integrate Redis, Cosmos DB, PostgreSQL, and AI Search in a cohesive solution


### Types of Agent Memory

This MicroHack will showcase:
- **Session memory**: Short-term message store in Redis
- **Conversation history**: Raw history of conversations with metadata (LLM-generated name, date), stored in Cosmos DB; main purpose is to show 7-day history in UI
- **Conversation memory**: Long-term memory of batch processed conversations (summaries, metadata, semantically searchable, no sensitive/explicit data), stored in PostgreSQL
- **User memory**: Extracted user information with automatic injection to the system prompt and tool-based write, stored in Cosmos DB
- **Knowledge base**: Document chunking pipeline, agentic/hybrid/semantic/keyword search, stored in AI Search
- **Agents Scratchpad**: Stack memory for multi-agent scenarios, read and write as a tool, stored in Redis
- **Knowledge graph**: Graph-based solution for advanced agentic search (GraphRAG): items, relationships, and higher-level concepts with descriptions, semantic search and connections; probably using PostgreSQL AGE or SQL (to be decided, optional advanced chapter)


## MicroHack Challenges

This MicroHack consists of progressive challenges to build your expertise:

| Challenge | Title | Focus Area | Duration |
|-----------|-------|------------|----------|
| 01 | **Session Memory** | Short-term message store in Redis | 45 min |
| 02 | **Conversation History** | Raw history, metadata, Cosmos DB, UI | 45 min |
| 03 | **Conversation Memory** | Summaries, semantic search, PostgreSQL | 60 min |
| 04 | **User Memory** | User info extraction, system prompt, Cosmos DB | 60 min |
| 05 | **Knowledge Base** | Document chunking, agentic/hybrid/semantic/keyword search, AI Search | 60 min |
| 06 | **Agents Scratchpad** | Stack memory, multi-agent workflows, Redis | 45 min |
| 07 | **Knowledge Graph** | Graph-based agentic search, GraphRAG, PostgreSQL AGE/SQL (optional, advanced) | 90 min |

## TODOs
- [x] Master prompt to JINJA
- [x] Apply Profile to Master prompt
- [ ] Add tool to update Profile
- [x] Add tool to retrieve from conversaton memory and inject to prompt
- [ ] convert tools to MCP


## Technologies Used

- Azure Cache for Redis
- Azure Cosmos DB
- Azure Database for PostgreSQL Flexible Server or HorizonDB
- Azure AI Search
- PostgreSQL AGE or Azure SQL
- Python (agents backend)
- JavaScript/TypeScript (UI)