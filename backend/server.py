# server.py
"""
AG-UI Customer Support Server with Server-Side Session Management

This server manages conversation history on the server side using Microsoft Agent Framework's
AgentThread and ChatMessageStore. Sessions are stored in-memory by default, with optional
Redis persistence for production deployments.

Architecture:
- SessionManager: Manages thread lifecycle (create, get, delete, list)
- AgentThread: Maintains per-session message history automatically
- ChatMessageStore: In-memory message storage per thread
- Custom AG-UI endpoint: Integrates session management with streaming responses
"""

import contextvars
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jinja2
from datetime import datetime
from typing import Annotated, Any
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import User, get_current_user
from conversation_history import ConversationHistoryStore
from conversation_memory import ConversationMemoryStore
from memory_agent import MemoryAgent
from rag_client import RAGClient
from user_profile_memory import UserProfileMemoryStore
from profile_agent import ProfileAgent

from agent_framework import ChatAgent, AgentThread, ChatMessageStore, tool
from agent_framework._threads import ChatMessage
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

# AG-UI event classes and encoder
from ag_ui.core.events import (
    RunStartedEvent,
    RunFinishedEvent,
    TextMessageContentEvent,
    ToolCallStartEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    RunErrorEvent,
)
from ag_ui.encoder import EventEncoder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ag_ui.server")

# Silence verbose Azure SDK HTTP logging by installing a reject-all filter.
# setLevel(WARNING) alone is not enough because the SDK may reconfigure loggers.
class _RejectAll(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return False

for _azure_logger_name in (
    "azure.cosmos._cosmos_http_logging_policy",
    "azure.core.pipeline.policies.http_logging_policy",
):
    _lg = logging.getLogger(_azure_logger_name)
    _lg.setLevel(logging.WARNING)
    _lg.addFilter(_RejectAll())
    _lg.propagate = False

# Load environment variables from .env file
load_dotenv()

# Validate environment configuration
openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
model_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

if not openai_endpoint:
    raise RuntimeError("Missing required environment variable: AZURE_OPENAI_ENDPOINT")
if not model_deployment:
    raise RuntimeError("Missing required environment variable: AZURE_OPENAI_DEPLOYMENT_NAME")

# =============================================================================
# Prompt Loading (Jinja2)
# =============================================================================

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=True,
    undefined=jinja2.StrictUndefined,
)

def load_prompt(template_name: str, **kwargs: object) -> str:
    """Render a Jinja2 prompt template from the prompts/ directory."""
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs).strip()

CUSTOMER_SUPPORT_PROMPT = load_prompt("customer_support.j2")


# =============================================================================
# Session Management
# =============================================================================

class SessionInfo(BaseModel):
    """Information about a chat session."""
    session_id: str
    title: str | None = None
    created_at: str
    message_count: int
    last_activity: str | None = None


class SessionManager:
    """
    Manages conversation sessions with server-side history storage.
    
    Each session maps to an AgentThread which maintains its own message history
    via ChatMessageStore. This enables:
    - Automatic context maintenance across turns
    - Session persistence without frontend state
    - Easy serialization for external storage (Redis, DB, etc.)
    """
    
    def __init__(self, max_sessions: int = 1000, max_messages_per_session: int = 100):
        """
        Initialize the session manager.
        
        Args:
            max_sessions: Maximum number of concurrent sessions (LRU eviction)
            max_messages_per_session: Maximum messages to retain per session
        """
        self._sessions: dict[str, AgentThread] = {}
        self._session_metadata: dict[str, dict[str, Any]] = {}
        self._max_sessions = max_sessions
        self._max_messages = max_messages_per_session
    
    def create_session(
        self,
        session_id: str | None = None,
        title: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """
        Create a new chat session with an empty message store.
        
        Args:
            session_id: Optional custom session ID. If None, generates a UUID.
            title: Optional human-readable title for the session.
            user_id: Owner user ID for this session.
        
        Returns:
            The session ID for the new session.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        # Evict oldest session if at capacity
        if len(self._sessions) >= self._max_sessions:
            oldest_id = min(
                self._session_metadata.keys(),
                key=lambda k: self._session_metadata[k].get("last_activity", "")
            )
            self.delete_session(oldest_id)
        
        # Create thread with in-memory message store
        message_store = ChatMessageStore(messages=[])
        thread = AgentThread(message_store=message_store)
        
        self._sessions[session_id] = thread
        self._session_metadata[session_id] = {
            "title": title,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "user_id": user_id,
        }
        
        return session_id
    
    def create_session_from_history(
        self,
        session_id: str,
        history_messages: list[dict[str, Any]],
        title: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """
        Create a session pre-populated with historical messages from Cosmos DB.
        
        Used when resuming a conversation whose live session has been evicted.
        """
        # Evict oldest session if at capacity
        if len(self._sessions) >= self._max_sessions:
            oldest_id = min(
                self._session_metadata.keys(),
                key=lambda k: self._session_metadata[k].get("last_activity", "")
            )
            self.delete_session(oldest_id)
        
        # Convert stored message dicts to ChatMessage objects
        chat_messages: list[ChatMessage] = []
        for msg in history_messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role in ("user", "assistant", "system"):
                chat_messages.append(ChatMessage(role=role, text=text))
        
        message_store = ChatMessageStore(messages=chat_messages)
        thread = AgentThread(message_store=message_store)
        
        self._sessions[session_id] = thread
        self._session_metadata[session_id] = {
            "title": title,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "user_id": user_id,
        }
        
        logger.info(
            "Restored session from history id=%s messages=%d",
            session_id,
            len(chat_messages),
        )
        return session_id
    
    def get_session(self, session_id: str, auto_create: bool = True) -> AgentThread | None:
        """
        Retrieve an existing session's thread.
        
        Args:
            session_id: The session ID to look up.
            auto_create: If True, creates a new session if not found.
        
        Returns:
            The AgentThread for the session, or None if not found and auto_create is False.
        """
        if session_id not in self._sessions:
            if auto_create:
                self.create_session(session_id)
            else:
                return None
        
        # Update last activity
        if session_id in self._session_metadata:
            self._session_metadata[session_id]["last_activity"] = datetime.utcnow().isoformat()
        
        return self._sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and its message history.
        
        Args:
            session_id: The session ID to delete.
        
        Returns:
            True if session was deleted, False if not found.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._session_metadata.pop(session_id, None)
            return True
        return False
    
    def update_session(self, session_id: str, title: str | None = None) -> bool:
        """
        Update session metadata.
        
        Args:
            session_id: The session ID to update.
            title: New title for the session (None leaves unchanged).
        
        Returns:
            True if session was updated, False if not found.
        """
        if session_id not in self._sessions:
            return False
        
        metadata = self._session_metadata.get(session_id, {})
        if title is not None:
            metadata["title"] = title
        metadata["last_activity"] = datetime.utcnow().isoformat()
        self._session_metadata[session_id] = metadata
        return True

    async def get_session_info(self, session_id: str) -> SessionInfo | None:
        """Get information about a specific session."""
        thread = self._sessions.get(session_id)
        if thread is None:
            return None
        
        metadata = self._session_metadata.get(session_id, {})
        message_count = 0
        
        if thread.message_store:
            messages = await thread.message_store.list_messages()
            message_count = len(messages) if messages else 0
        
        return SessionInfo(
            session_id=session_id,
            title=metadata.get("title"),
            created_at=metadata.get("created_at", "unknown"),
            message_count=message_count,
            last_activity=metadata.get("last_activity"),
        )
    
    async def list_sessions(self, user_id: str | None = None) -> list[SessionInfo]:
        """List active sessions, optionally filtered by user."""
        sessions = []
        for session_id in self._sessions:
            if user_id is not None:
                meta = self._session_metadata.get(session_id, {})
                if meta.get("user_id") != user_id:
                    continue
            info = await self.get_session_info(session_id)
            if info:
                sessions.append(info)
        return sessions
    
    async def get_session_history(self, session_id: str) -> list[dict[str, Any]] | None:
        """
        Get the full message history for a session.
        
        Returns a list of message dicts with role and content.
        """
        thread = self._sessions.get(session_id)
        if thread is None or thread.message_store is None:
            return None
        
        messages = await thread.message_store.list_messages()
        if messages is None:
            return []
        
        result = []
        for msg in messages:
            role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
            text = msg.text if hasattr(msg, 'text') and msg.text else ""

            # Extract tool calls and results from contents
            tool_calls = []
            tool_results = []
            for c in (msg.contents or []):
                ctype = getattr(c, 'type', None)
                if ctype == 'function_call':
                    tool_calls.append({
                        "call_id": getattr(c, 'call_id', None),
                        "name": getattr(c, 'name', None),
                        "arguments": getattr(c, 'arguments', None),
                    })
                elif ctype == 'function_result':
                    res = getattr(c, 'result', None)
                    tool_results.append({
                        "call_id": getattr(c, 'call_id', None),
                        "result": json.dumps(res) if isinstance(res, (dict, list)) else str(res) if res else "",
                    })

            entry: dict[str, Any] = {"role": role, "content": text}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            if tool_results:
                entry["tool_results"] = tool_results
            result.append(entry)
        return result


# Initialize the session manager
session_manager = SessionManager(max_sessions=1000, max_messages_per_session=100)

# Initialize the conversation history store (Cosmos DB)
conversation_store = ConversationHistoryStore()

# Initialize the conversation memory store (PostgreSQL + pgvector)
memory_store = ConversationMemoryStore()

# Initialize the user profile memory store (Cosmos DB)
profile_store = UserProfileMemoryStore()

# Initialize the RAG client (Azure AI Search knowledge base)
rag_client = RAGClient()


# =============================================================================
# Tools
# =============================================================================

# ContextVar to propagate the current user_id into @tool functions
_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_user_id")

def json_merge_patch(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """RFC 7396 JSON Merge Patch — recursive merge with null-removal."""
    result = dict(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = json_merge_patch(result[key], value)
        else:
            result[key] = value
    return result


# Status → Material Symbol icon name mapping
_STATUS_ICONS = {
    "shipped": "local_shipping",
    "processing": "pending",
    "delivered": "check_circle",
    "not_found": "error",
}


@tool
async def check_memory(
    query: Annotated[str, Field(description="Natural-language query to search past conversations")],
) -> str:
    """Search the user's conversation memory for relevant past conversations.

    Use this tool when the user explicitly references or asks about something
    from a previous conversation. Returns the top 3 most relevant conversation
    summaries based on semantic similarity.
    """
    user_id = _current_user_id.get()
    logger.info("Running check_memory tool with query: %s for user: %s", query, user_id)
    query_embedding = await memory_agent._embed(query)

    rows = await memory_store.search(
        user_id=user_id,
        query_embedding=query_embedding,
        limit=3,
    )

    if not rows:
        logger.info("No relevant past conversations found for query: %s", query)
        return "No relevant past conversations found."
    
    logger.info("Found %d relevant conversations for query: %s", len(rows), query)
    results = []
    for i, row in enumerate(rows, 1):
        results.append(f"{i}. {row['summary']}")

    return "\n".join(results)


@tool
def get_order_status(
    order_id: Annotated[str, Field(description="The order ID to look up (e.g., ORD-001)")]
) -> dict:
    """Look up the status of a customer order.

    Returns a data model ready for the Shipping Status A2UI template:
      trackingNumber  – display string with tracking code
      currentStepIcon – Material Symbol name for the active step
      eta             – estimated delivery display string
    """
    orders = {
        "ORD-001": {"status": "shipped",    "tracking": "1Z999AA1", "eta": "Jan 25, 2026"},
        "ORD-002": {"status": "processing", "tracking": None,       "eta": "Jan 23, 2026"},
        "ORD-003": {"status": "delivered",  "tracking": "1Z999AA3", "eta": "Delivered Jan 20"},
    }
    raw = orders.get(order_id)

    if raw is None:
        return {
            "trackingNumber": "Tracking: N/A",
            "currentStepIcon": "error",
            "eta": "Order not found",
        }

    return {
        "trackingNumber": f"Tracking: {raw['tracking']}" if raw.get("tracking") else "Tracking: N/A",
        "currentStepIcon": _STATUS_ICONS.get(raw["status"], "help"),
        "eta": f"Estimated delivery: {raw['eta']}" if raw.get("eta") else "",
    }


@tool
async def do_rag(
    query: Annotated[str, Field(description="Natural-language question to search the knowledge base for")],
) -> dict:
    """Search the company knowledge base for detailed information about orders,
    products, shipping, and return/refund policies.

    Use this tool when you need:
    - Detailed product specifications or descriptions
    - Shipping carrier, weight, or packaging information
    - Return policy rules, eligibility windows, or refund timelines
    - Any information beyond the basic order status

    Do NOT use this tool for a simple order status check — use
    get_order_status for that instead.
    """
    logger.info("Running do_rag tool with query: %s", query)
    try:
        result = await rag_client.retrieve(query=query)
    except Exception as e:
        logger.error("do_rag tool failed: %s", e, exc_info=True)
        return {"content": f"Knowledge base search failed: {e}", "citations": []}

    if not result.content and not result.citations:
        return {"content": "No relevant information found in the knowledge base.", "citations": []}

    citations_list = []
    for i, cit in enumerate(result.citations):
        citations_list.append({
            "search_idx": i,
            "ref_id": cit.ref_id,
            "source_name": cit.source_name,
            "content": cit.content,
            "annotation": f"\u3010{i}:{cit.ref_id}\u2020{cit.source_name}\u3011",
        })

    return {
        "content": result.content,
        "citations": citations_list,
    }


@tool
async def update_user_profile(
    basic_info: Annotated[dict[str, Any] | None, Field(
        default=None,
        description="Object with keys like name, location, job, company. Only include changed fields.",
    )] = None,
    interests: Annotated[list[str] | None, Field(
        default=None,
        description="Full list of user interests (merge new items with existing ones).",
    )] = None,
    habits: Annotated[list[str] | None, Field(
        default=None,
        description="Full list of user habits (merge new items with existing ones).",
    )] = None,
    preferences: Annotated[dict[str, Any] | None, Field(
        default=None,
        description="Object with user preferences. Only include changed fields.",
    )] = None,
    status: Annotated[dict[str, Any] | None, Field(
        default=None,
        description="Object with current life status or events. Only include changed fields.",
    )] = None,
    facts: Annotated[list[str] | None, Field(
        default=None,
        description="Full list of personal facts (pets, allergies, family, birthday, etc.).",
    )] = None,
) -> str:
    """Update the user's stored profile with new personal information.

    Call this when the user explicitly mentions new or changed personal
    information. Pass only the fields that changed.
    """
    user_id = _current_user_id.get()

    # Build patch from non-None arguments
    patch_dict: dict[str, Any] = {}
    if basic_info is not None:
        patch_dict["basic_info"] = basic_info
    if interests is not None:
        patch_dict["interests"] = interests
    if habits is not None:
        patch_dict["habits"] = habits
    if preferences is not None:
        patch_dict["preferences"] = preferences
    if status is not None:
        patch_dict["status"] = status
    if facts is not None:
        patch_dict["facts"] = facts

    logger.info("Running update_user_profile tool for user: %s with patch: %s", user_id, patch_dict)

    if not patch_dict:
        return "No profile fields provided"

    # Read current profile
    existing = await profile_store.get_profile(user_id)
    existing_sections: dict[str, Any] = {
        "basic_info": {},
        "interests": [],
        "habits": [],
        "preferences": {},
        "status": {},
        "facts": [],
    }
    if existing:
        for key in existing_sections:
            if key in existing:
                existing_sections[key] = existing[key]

    # Apply merge patch
    merged = json_merge_patch(existing_sections, patch_dict)

    # Upsert to Cosmos DB
    await profile_store.upsert_profile(
        user_id=user_id,
        profile_sections=merged,
        source_conversation=None,
    )

    # Return summary
    changed_keys = list(patch_dict.keys())
    summary = f"Profile updated: {', '.join(changed_keys)}"
    logger.info("Profile updated for user=%s: %s", user_id, summary)
    return summary


# =============================================================================
# Agent Configuration
# =============================================================================

# Initialize Azure OpenAI Chat client
chat_client = AzureOpenAIChatClient(
    credential=DefaultAzureCredential(),
    endpoint=openai_endpoint,
    deployment_name=model_deployment,
)

# Configure the default agent (no profile — used as fallback)
agent = ChatAgent(
    name="CustomerSupportAgent",
    instructions=CUSTOMER_SUPPORT_PROMPT,
    chat_client=chat_client,
    tools=[get_order_status, check_memory, do_rag, update_user_profile],
)


def _build_personalized_agent(
    user_profile: dict[str, Any] | None,
    *,
    rag_enabled: bool = True,
) -> ChatAgent:
    """Return an agent whose system prompt is enriched with the user profile.

    If *user_profile* is ``None`` or empty the global default agent is
    returned so we avoid an unnecessary re-render.
    """
    tools = [get_order_status, check_memory, update_user_profile]
    if rag_enabled:
        tools.append(do_rag)

    if not user_profile and rag_enabled:
        return agent  # global default already has all tools

    prompt = load_prompt(
        "customer_support.j2",
        user_profile=user_profile,
        rag_enabled=rag_enabled,
    )
    return ChatAgent(
        name="CustomerSupportAgent",
        instructions=prompt,
        chat_client=chat_client,
        tools=tools,
    )


# Initialize the memory agent (summariser + embedder) — must be after chat_client
memory_agent = MemoryAgent(chat_client=chat_client)

# Initialize the profile agent (user profile extraction) — must be after chat_client
profile_agent = ProfileAgent(chat_client=chat_client)


# =============================================================================
# FastAPI Application
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup: Initialize Cosmos DB and PostgreSQL
    await conversation_store.initialize()
    logger.info("Conversation history store initialized (Cosmos DB)")
    await memory_store.initialize()
    logger.info("Conversation memory store initialized (PostgreSQL)")
    await profile_store.initialize()
    logger.info("User profile memory store initialized (Cosmos DB)")
    
    yield
    
    # Shutdown: Close Cosmos DB and PostgreSQL clients
    await conversation_store.close()
    logger.info("Conversation history store closed")
    await memory_store.close()
    logger.info("Conversation memory store closed")
    await profile_store.close()
    logger.info("User profile memory store closed")


app = FastAPI(
    title="AG-UI Customer Support Server",
    description="Interactive AI agent server with server-side session management and AG-UI protocol support",
    lifespan=lifespan,
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID"],
)


# =============================================================================
# Auth helpers
# =============================================================================

def _assert_session_owner(session_id: str, user_id: str) -> None:
    """Raise 403 if the session does not belong to the user."""
    meta = session_manager._session_metadata.get(session_id)
    if meta is None:
        return  # session doesn't exist yet — will 404 later
    if meta.get("user_id") is not None and meta["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")


@app.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user profile."""
    return current_user


@app.get("/prompts/{prompt_name}")
async def get_prompt(
    prompt_name: str,
    current_user: User = Depends(get_current_user),
):
    """Return the rendered system prompt for the given template name.

    If the current user has a stored profile, the prompt is rendered with
    personalised context injected.
    """
    template_file = f"{prompt_name}.j2"
    user_profile = await profile_store.get_profile(current_user.user_id)
    try:
        rendered = load_prompt(template_file, user_profile=user_profile)
    except jinja2.TemplateNotFound:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' not found")
    return {"name": prompt_name, "content": rendered}


# Request/Response Models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    messages: list[dict[str, str]] = Field(
        default=[],
        description="Message history (optional if session has history)"
    )
    thread_id: str | None = Field(
        default=None,
        description="Session/thread ID. If not provided, creates a new session."
    )
    rag_enabled: bool = Field(
        default=True,
        description="Whether knowledge base search (RAG) is enabled for this request."
    )


class CreateSessionRequest(BaseModel):
    """Request model for creating a new session."""
    session_id: str | None = Field(
        default=None,
        description="Optional custom session ID"
    )
    title: str | None = Field(
        default=None,
        description="Optional human-readable title for the session"
    )


class UpdateSessionRequest(BaseModel):
    """Request model for updating a session."""
    title: str | None = Field(
        default=None,
        description="New title for the session"
    )


class CreateSessionResponse(BaseModel):
    """Response model for session creation."""
    session_id: str
    title: str | None = None
    message: str


# =============================================================================
# Session Management Endpoints
# =============================================================================

@app.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest | None = None,
    current_user: User = Depends(get_current_user),
):
    """Create a new chat session."""
    session_id = session_manager.create_session(
        session_id=request.session_id if request else None,
        title=request.title if request else None,
        user_id=current_user.user_id,
    )
    return CreateSessionResponse(
        session_id=session_id,
        title=request.title if request else None,
        message="Session created successfully",
    )


@app.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(current_user: User = Depends(get_current_user)):
    """List sessions for the current user."""
    return await session_manager.list_sessions(user_id=current_user.user_id)


@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get information about a specific session."""
    _assert_session_owner(session_id, current_user.user_id)
    info = await session_manager.get_session_info(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return info


@app.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the full message history for a session."""
    _assert_session_owner(session_id, current_user.user_id)
    history = await session_manager.get_session_history(session_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": history}


@app.put("/sessions/{session_id}", response_model=SessionInfo)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    current_user: User = Depends(get_current_user),
):
    """Update session metadata (e.g. title)."""
    _assert_session_owner(session_id, current_user.user_id)
    if not session_manager.update_session(session_id, title=request.title):
        raise HTTPException(status_code=404, detail="Session not found")
    info = await session_manager.get_session_info(session_id)
    return info


@app.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a session and its history (also removes from Cosmos DB)."""
    _assert_session_owner(session_id, current_user.user_id)
    if session_manager.delete_session(session_id):
        # Also remove from durable conversation history
        await conversation_store.delete_conversation(session_id, current_user.user_id)
        return {"message": "Session deleted successfully"}
    raise HTTPException(status_code=404, detail="Session not found")


# =============================================================================
# Conversation History Endpoints (Cosmos DB)
# =============================================================================

class ConversationSummary(BaseModel):
    """Lightweight conversation summary for list views."""
    id: str
    user_id: str
    title: str | None = None
    created_at: str
    updated_at: str
    message_count: int


class UpdateConversationRequest(BaseModel):
    """Request model for updating a conversation."""
    title: str | None = None


@app.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """List all conversations for the current user (from Cosmos DB)."""
    items = await conversation_store.list_conversations(
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )
    return [
        ConversationSummary(
            id=item["id"],
            user_id=item["user_id"],
            title=item.get("title"),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            message_count=item.get("message_count", 0),
        )
        for item in items
    ]


@app.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a full conversation with messages from Cosmos DB."""
    doc = await conversation_store.get_conversation(conversation_id, current_user.user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": doc["id"],
        "user_id": doc["user_id"],
        "title": doc.get("title"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "message_count": doc.get("message_count", 0),
        "messages": doc.get("messages", []),
        "metadata": doc.get("metadata", {}),
    }


@app.put("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    current_user: User = Depends(get_current_user),
):
    """Update conversation metadata (e.g. title) in Cosmos DB."""
    if request.title is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    result = await conversation_store.update_title(conversation_id, current_user.user_id, request.title)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": conversation_id, "title": request.title, "message": "Conversation updated"}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Hard-delete a conversation from Cosmos DB."""
    deleted = await conversation_store.delete_conversation(conversation_id, current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Cascade: also remove any associated memory
    await memory_store.delete_memory(conversation_id, current_user.user_id)
    return {"message": "Conversation deleted successfully"}


# =============================================================================
# Conversation Memory Endpoints (PostgreSQL + pgvector)
# =============================================================================

class CreateMemoryRequest(BaseModel):
    """Request model for creating a conversation memory."""
    conversation_id: str = Field(description="ID of the conversation to memorise")


class MemorySummaryResponse(BaseModel):
    """Response model for a single memory item."""
    id: str
    conversation_id: str
    user_id: str
    summary: str
    source_title: str | None = None
    message_count: int = 0
    created_at: str
    updated_at: str


class MemorySearchRequest(BaseModel):
    """Request model for vector search over memories."""
    query: str = Field(description="Natural-language search query")
    limit: int = Field(default=10, ge=1, le=50)


class MemorySearchResultItem(BaseModel):
    """A single search result with similarity score."""
    id: str
    conversation_id: str
    summary: str
    source_title: str | None = None
    similarity: float
    created_at: str


class MemorySearchResponse(BaseModel):
    """Response model for memory search."""
    query: str
    results: list[MemorySearchResultItem]


def _row_to_memory_response(row: dict) -> MemorySummaryResponse:
    """Convert a database row dict to the API response model."""
    return MemorySummaryResponse(
        id=str(row["id"]),
        conversation_id=row["conversation_id"],
        user_id=row["user_id"],
        summary=row["summary"],
        source_title=row.get("source_title"),
        message_count=row.get("message_count", 0),
        created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
    )


@app.post("/memories", response_model=MemorySummaryResponse, status_code=201)
async def create_memory(
    request: CreateMemoryRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Create a conversation memory (summary + embedding) for a conversation.

    Fetches the full conversation from Cosmos DB, runs the summarisation agent,
    generates an embedding, and stores the result in PostgreSQL.
    """
    # 1. Validate ownership and fetch the conversation
    conversation = await conversation_store.get_conversation(
        request.conversation_id, current_user.user_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conversation.get("messages", [])
    if not messages:
        raise HTTPException(status_code=422, detail="Conversation has no messages to summarise")

    # 2. Run memory agent (summarise + embed)
    result = await memory_agent.create_memory(
        conversation_messages=messages,
        title=conversation.get("title"),
    )

    # 3. Persist to PostgreSQL
    row = await memory_store.create_memory(
        conversation_id=request.conversation_id,
        user_id=current_user.user_id,
        summary=result.summary,
        embedding=result.embedding,
        source_title=conversation.get("title"),
        message_count=conversation.get("message_count", len(messages)),
    )

    return _row_to_memory_response(row)


@app.get("/memories", response_model=list[MemorySummaryResponse])
async def list_memories(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """List all conversation memories for the current user."""
    rows = await memory_store.list_memories(
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )
    return [_row_to_memory_response(r) for r in rows]


@app.get("/memories/{conversation_id}", response_model=MemorySummaryResponse)
async def get_memory(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a single conversation memory."""
    row = await memory_store.get_memory(conversation_id, current_user.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _row_to_memory_response(row)


@app.delete("/memories/{conversation_id}")
async def delete_memory(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation memory."""
    deleted = await memory_store.delete_memory(conversation_id, current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Memory deleted successfully"}


@app.post("/memories/search", response_model=MemorySearchResponse)
async def search_memories(
    request: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Semantic search over conversation memories.

    Generates an embedding for the query text, then performs cosine-similarity
    search in PostgreSQL (pgvector) scoped to the current user.
    """
    # Generate embedding for the search query
    query_embedding = await memory_agent._embed(request.query)

    # Search
    rows = await memory_store.search(
        user_id=current_user.user_id,
        query_embedding=query_embedding,
        limit=request.limit,
    )

    results = [
        MemorySearchResultItem(
            id=str(r["id"]),
            conversation_id=r["conversation_id"],
            summary=r["summary"],
            source_title=r.get("source_title"),
            similarity=float(r.get("similarity", 0)),
            created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
        )
        for r in rows
    ]

    return MemorySearchResponse(query=request.query, results=results)


# =============================================================================
# User Profile Memory Endpoints (Cosmos DB)
# =============================================================================

class GenerateProfileRequest(BaseModel):
    """Request model for generating a user profile from one conversation."""
    conversation_id: str = Field(description="ID of the conversation to extract profile data from")


class GenerateAllProfilesRequest(BaseModel):
    """Request model for generating a user profile from all conversations."""
    limit: int = Field(default=20, ge=1, le=100, description="Max conversations to process")


class UpdateProfileRequest(BaseModel):
    """Request model for manually editing a user profile."""
    basic_info: dict[str, str | None] | None = None
    interests: list[str] | None = None
    habits: list[str] | None = None
    preferences: dict[str, str | None] | None = None
    status: dict[str, str | None] | None = None
    facts: list[str] | None = None


class UserProfileResponse(BaseModel):
    """Response model for a user profile."""
    user_id: str
    version: int = 1
    basic_info: dict = {}
    interests: list[str] = []
    habits: list[str] = []
    preferences: dict = {}
    status: dict = {}
    facts: list[str] = []
    source_conversations: list[dict] = []
    created_at: str = ""
    updated_at: str = ""


class GenerateProfileResponse(BaseModel):
    """Response for single-conversation profile generation."""
    profile_changed: bool
    change_summary: str
    profile: UserProfileResponse


class GenerateAllProfilesResponse(BaseModel):
    """Response for multi-conversation profile generation."""
    profile_changed: bool
    conversations_processed: int
    conversations_skipped: int
    change_summary: str
    profile: UserProfileResponse


def _doc_to_profile_response(doc: dict) -> UserProfileResponse:
    """Convert a Cosmos DB document to a UserProfileResponse."""
    return UserProfileResponse(
        user_id=doc.get("user_id", ""),
        version=doc.get("version", 1),
        basic_info=doc.get("basic_info", {}),
        interests=doc.get("interests", []),
        habits=doc.get("habits", []),
        preferences=doc.get("preferences", {}),
        status=doc.get("status", {}),
        facts=doc.get("facts", []),
        source_conversations=doc.get("source_conversations", []),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


@app.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
):
    """Get the current user's profile."""
    doc = await profile_store.get_profile(current_user.user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="No profile found. Use 'Generate Profile' to create one.")
    return _doc_to_profile_response(doc)


@app.post("/profile/generate", response_model=GenerateProfileResponse)
async def generate_profile(
    request: GenerateProfileRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate or update the user profile from a single conversation."""
    # 1. Validate ownership
    conversation = await conversation_store.get_conversation(
        request.conversation_id, current_user.user_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conversation.get("messages", [])
    if not messages:
        raise HTTPException(status_code=422, detail="Conversation has no messages")

    # 2. Read existing profile
    existing = await profile_store.get_profile(current_user.user_id)

    # 3. Run profile agent
    result = await profile_agent.extract_profile(
        existing_profile=existing,
        conversation_messages=messages,
        conversation_id=request.conversation_id,
    )

    # 4. Persist if changed
    if result.changed:
        source_conv = {
            "conversation_id": request.conversation_id,
            "extracted_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "facts_added": result.facts_added,
            "facts_updated": result.facts_updated,
            "facts_removed": result.facts_removed,
        }
        doc = await profile_store.upsert_profile(
            user_id=current_user.user_id,
            profile_sections=result.profile,
            source_conversation=source_conv,
        )
    else:
        doc = existing or {
            "user_id": current_user.user_id,
            "version": 0,
            **result.profile,
            "source_conversations": [],
            "created_at": "",
            "updated_at": "",
        }

    return GenerateProfileResponse(
        profile_changed=result.changed,
        change_summary=result.summary,
        profile=_doc_to_profile_response(doc),
    )


@app.post("/profile/generate-all", response_model=GenerateAllProfilesResponse)
async def generate_profile_from_all(
    request: GenerateAllProfilesRequest | None = None,
    current_user: User = Depends(get_current_user),
):
    """Generate or update the user profile from all recent conversations."""
    limit = request.limit if request else 20

    # 1. Read existing profile
    existing = await profile_store.get_profile(current_user.user_id)

    # 2. List conversations
    conversations = await conversation_store.list_conversations(
        user_id=current_user.user_id,
        limit=limit,
    )

    # 3. Determine which conversations are already processed
    processed_ids: set[str] = set()
    if existing and existing.get("source_conversations"):
        processed_ids = {sc["conversation_id"] for sc in existing["source_conversations"]}

    new_conversations = [c for c in conversations if c["id"] not in processed_ids]
    skipped = len(conversations) - len(new_conversations)
    processed = 0
    overall_changed = False
    overall_summary_parts: list[str] = []
    current_profile = existing

    # 4. Process each new conversation sequentially
    for conv_summary in new_conversations:
        conv_id = conv_summary["id"]
        conv_detail = await conversation_store.get_conversation(conv_id, current_user.user_id)
        if not conv_detail:
            continue
        messages = conv_detail.get("messages", [])
        if not messages:
            continue

        result = await profile_agent.extract_profile(
            existing_profile=current_profile,
            conversation_messages=messages,
            conversation_id=conv_id,
        )

        processed += 1
        if result.changed:
            overall_changed = True
            overall_summary_parts.append(result.summary)
            source_conv = {
                "conversation_id": conv_id,
                "extracted_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
                "facts_added": result.facts_added,
                "facts_updated": result.facts_updated,
                "facts_removed": result.facts_removed,
            }
            current_profile = await profile_store.upsert_profile(
                user_id=current_user.user_id,
                profile_sections=result.profile,
                source_conversation=source_conv,
            )

    if not overall_changed:
        overall_summary = "No new personal information found in any conversation"
    else:
        overall_summary = "; ".join(overall_summary_parts)

    doc = current_profile or {
        "user_id": current_user.user_id,
        "version": 0,
        "basic_info": {},
        "interests": [],
        "habits": [],
        "preferences": {},
        "status": {},
        "facts": [],
        "source_conversations": [],
        "created_at": "",
        "updated_at": "",
    }

    return GenerateAllProfilesResponse(
        profile_changed=overall_changed,
        conversations_processed=processed,
        conversations_skipped=skipped,
        change_summary=overall_summary,
        profile=_doc_to_profile_response(doc),
    )


@app.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
):
    """Manually edit the user profile (partial update)."""
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Check if profile exists; if not, create with provided fields
    existing = await profile_store.get_profile(current_user.user_id)
    if existing is None:
        # Create a new profile with the provided fields
        sections = {
            "basic_info": request.basic_info or {},
            "interests": request.interests or [],
            "habits": request.habits or [],
            "preferences": request.preferences or {},
            "status": request.status or {},
            "facts": request.facts or [],
        }
        doc = await profile_store.upsert_profile(
            user_id=current_user.user_id,
            profile_sections=sections,
        )
    else:
        doc = await profile_store.patch_profile(current_user.user_id, updates)
        if doc is None:
            raise HTTPException(status_code=404, detail="Profile not found")

    return _doc_to_profile_response(doc)


@app.delete("/profile")
async def delete_profile(
    current_user: User = Depends(get_current_user),
):
    """Delete the current user's profile."""
    deleted = await profile_store.delete_profile(current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No profile found")
    return {"message": "Profile deleted successfully"}


# =============================================================================
# AG-UI Chat Endpoint with Server-Side History
# =============================================================================

async def _persist_conversation(session_id: str, user_id: str, title: str | None) -> None:
    """Persist current session history to Cosmos DB after a completed run."""
    try:
        history = await session_manager.get_session_history(session_id)
        if history is not None:
            metadata = {
                "agent_name": "CustomerSupportAgent",
                "model_deployment": model_deployment,
            }
            await conversation_store.save_conversation(
                session_id=session_id,
                user_id=user_id,
                messages=history,
                title=title,
                metadata=metadata,
            )
    except Exception as e:
        logger.error("Failed to persist conversation id=%s: %s", session_id, str(e), exc_info=True)


async def stream_agent_response(
    user_message: str,
    thread: AgentThread,
    session_id: str,
    user_id: str,
    personalized_agent: ChatAgent | None = None,
) -> AsyncIterator[str]:
    """
    Stream agent response using AG-UI protocol.
    
    The AgentThread automatically maintains message history, so we just need to:
    1. Run the agent with the thread
    2. Stream AG-UI events
    3. History is automatically updated by the framework
    """
    encoder = EventEncoder()
    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())  # Message ID for text content events
    
    logger.info("[IN] session=%s run=%s user_message=%s", session_id, run_id, user_message)

    # Set the current user_id so @tool functions can access it
    _current_user_id.set(user_id)

    # Emit RUN_STARTED with thread/session ID
    logger.info("[OUT] session=%s run=%s event=RUN_STARTED", session_id, run_id)
    yield encoder.encode(RunStartedEvent(thread_id=session_id, run_id=run_id))
    
    try:
        # Track tool calls to deduplicate
        seen_tools: set[str] = set()
        full_response_text: list[str] = []  # accumulate text deltas
        
        # Use personalized agent if available, otherwise fall back to default
        active_agent = personalized_agent or agent
        # Stream agent response - framework handles history automatically
        async for update in active_agent.run_stream(user_message, thread=thread):
            # Emit text content
            if update.text:
                full_response_text.append(update.text)
                logger.debug("[OUT] session=%s run=%s event=TEXT_CONTENT delta=%s", session_id, run_id, update.text)
                yield encoder.encode(TextMessageContentEvent(
                    messageId=message_id,
                    delta=update.text,
                ))
            
            # Emit tool calls and results from contents
            for content in update.contents:
                content_dict = content.to_dict() if hasattr(content, 'to_dict') else {}
                content_type = content_dict.get('type', '')
                
                if content_type == 'function_call':
                    call_id = content_dict.get('call_id', '')
                    if call_id and call_id not in seen_tools:
                        seen_tools.add(call_id)
                        tool_name = content_dict.get('name', 'unknown')
                        # Log full content_dict to capture args regardless of key name
                        logger.info("[OUT] session=%s run=%s event=TOOL_CALL_START tool=%s call_id=%s content=%s",
                                    session_id, run_id, tool_name, call_id,
                                    json.dumps(content_dict, default=str))
                        yield encoder.encode(ToolCallStartEvent(
                            toolCallId=call_id,
                            toolCallName=tool_name,
                        ))
                elif content_type == 'function_result':
                    call_id = content_dict.get('call_id', '')
                    result_key = f"result_{call_id}"
                    if result_key not in seen_tools:
                        seen_tools.add(result_key)
                        # Emit tool result event - use json.dumps for valid JSON
                        result_data = content_dict.get('result', '')
                        result_content = json.dumps(result_data) if isinstance(result_data, (dict, list)) else str(result_data)
                        logger.info("[OUT] session=%s run=%s event=TOOL_CALL_RESULT call_id=%s result=%s",
                                    session_id, run_id, call_id, result_content)
                        yield encoder.encode(ToolCallResultEvent(
                            messageId=str(uuid.uuid4()),
                            toolCallId=call_id,
                            content=result_content,
                        ))
                        # Emit tool call end event
                        logger.info("[OUT] session=%s run=%s event=TOOL_CALL_END call_id=%s", session_id, run_id, call_id)
                        yield encoder.encode(ToolCallEndEvent(toolCallId=call_id))
        
        # Log the full assembled assistant response
        assistant_message = "".join(full_response_text)
        logger.info("[OUT] session=%s run=%s event=RUN_FINISHED response=%s", session_id, run_id, assistant_message)
        yield encoder.encode(RunFinishedEvent(thread_id=session_id, run_id=run_id))

        # Persist conversation to Cosmos DB after every completed run
        session_title = session_manager._session_metadata.get(session_id, {}).get("title")
        await _persist_conversation(session_id, user_id, session_title)

    except Exception as e:
        logger.error("[OUT] session=%s run=%s event=RUN_ERROR error=%s", session_id, run_id, str(e), exc_info=True)
        yield encoder.encode(RunErrorEvent(
            message=str(e),
            code="AGENT_ERROR",
        ))


@app.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """
    AG-UI compatible chat endpoint with server-side session management.
    
    - If thread_id is provided, uses existing session (creates if not found)
    - If thread_id is not provided, creates a new session
    - Message history is maintained server-side via AgentThread
    - Frontend only needs to send the new user message
    """
    # Get or create session
    session_id = request.thread_id or str(uuid.uuid4())
    # If session already exists, verify ownership
    if session_id in session_manager._sessions:
        _assert_session_owner(session_id, current_user.user_id)
    else:
        # Session not in memory — check if conversation history exists in Cosmos DB
        # so we can resume with full context instead of starting fresh.
        conversation = await conversation_store.get_conversation(
            session_id, current_user.user_id
        )
        if conversation and conversation.get("messages"):
            session_manager.create_session_from_history(
                session_id,
                history_messages=conversation["messages"],
                title=conversation.get("title"),
                user_id=current_user.user_id,
            )
            logger.info(
                "Resumed conversation from Cosmos DB id=%s messages=%d",
                session_id,
                len(conversation["messages"]),
            )
        else:
            session_manager.create_session(session_id, user_id=current_user.user_id)
    thread = session_manager.get_session(session_id, auto_create=False)
    
    if thread is None:
        raise HTTPException(status_code=500, detail="Failed to create session")
    
    # Extract user message from request
    # Priority: last user message in messages array, or use empty if none
    user_message = ""
    if request.messages:
        for msg in reversed(request.messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
    
    if not user_message:
        raise HTTPException(status_code=400, detail="No user message provided")

    # Fetch user profile to personalise the agent's system prompt
    user_profile = await profile_store.get_profile(current_user.user_id)
    personalized = _build_personalized_agent(user_profile, rag_enabled=request.rag_enabled)

    return StreamingResponse(
        stream_agent_response(user_message, thread, session_id, current_user.user_id, personalized),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id,
        }
    )


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Entry point for the AG-UI server."""
    import uvicorn
    print("Starting AG-UI server on http://localhost:8000")
    print("Server-side session management enabled")
    print("API docs available at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
