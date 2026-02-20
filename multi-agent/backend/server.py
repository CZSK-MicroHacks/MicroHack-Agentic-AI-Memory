# server.py
"""
FastAPI server for the multi-agent travel planning demo.

Endpoints:
- POST /chat: Start a travel planning workflow (SSE stream)
- GET /state: Get current workflow state (task board + document)
"""

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

from events import EventEmitter
from orchestrator import run_workflow

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("travel.server")

# Azure OpenAI setup
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
api_key = os.getenv("AZURE_OPENAI_API_KEY", "")

if api_key:
    chat_client = AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment,
        api_key=api_key,
    )
else:
    chat_client = AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment,
        credential=DefaultAzureCredential(),
    )

logger.info("Azure OpenAI configured: endpoint=%s, deployment=%s", endpoint, deployment)

# Current workflow state for /state endpoint
_current_state: dict[str, Any] = {
    "status": "idle",
    "tasks": [],
    "document": {"content": "", "versions": []},
}

app = FastAPI(title="Multi-Agent Travel Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(request: ChatRequest):
    """Start a multi-agent travel planning workflow. Returns an SSE stream."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    emitter = EventEmitter()

    # Run the workflow in the background, streaming events via the emitter
    async def _run():
        try:
            await run_workflow(request.message, chat_client, emitter)
        except Exception as e:
            logger.error("Workflow failed: %s", e, exc_info=True)
            await emitter.emit("error", {"message": str(e)})
            await emitter.done()

    asyncio.create_task(_run())

    return StreamingResponse(
        emitter.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/state")
async def get_state():
    """Get current workflow state (for late-joining UI or refresh)."""
    return _current_state


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
