import json
from typing import List, Optional, Dict, Any, AsyncGenerator
import asyncio

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from agent import server
from agent.utils.mcp_util import load_mcp_tools
from agent.utils.logger import get_logger

logger = get_logger("webapp")


# Pydantic models for OpenAI-compatible API
class ChatMessage(BaseModel):
    role: str = Field(..., description="The role of the message author (system, user, assistant)")
    content: str = Field(..., description="The content of the message")


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="cai-coder", description="Model identifier")
    messages: List[ChatMessage] = Field(..., description="List of messages in the conversation")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="Maximum tokens to generate")
    stream: Optional[bool] = Field(default=False, description="Whether to stream responses")
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    frequency_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0, description="Frequency penalty")
    presence_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0, description="Presence penalty")

class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Usage

class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    """Health check endpoint"""
    logger.debug("Health check request")
    return {"status": "healthy"}


@app.get("/v1/models")
async def list_models():
    """List available models"""
    return {
        "object": "list",
        "data": [
            {
                "id": "cai-coder",
                "object": "model",
                "created": 1687882410,
                "owned_by": "cai-coder"
            }
        ]
    }

_agent_instance = None
_agent_lock = asyncio.Lock()

async def get_agent():
    global _agent_instance
    async with _agent_lock:
        if _agent_instance is None:
            logger.debug("Loading MCP tools...")
            mcp_tools = await load_mcp_tools()
            logger.debug(f"Successfully loaded {len(mcp_tools)} MCP tools")

            _agent_instance = server.get_agent(
                checkpointer= InMemorySaver(),
                mcptools=mcp_tools
            )

            logger.debug("Agent instance created successfully")
        return _agent_instance


def generate_completion_id() -> str:
    """Generate a unique completion ID"""
    import uuid
    return f"chatcmpl-{uuid.uuid4().hex}"


async def stream_chat_completion(
        messages: List[ChatMessage],
        completion_id: str,
        model: str
) -> AsyncGenerator[str, None]:
    """Stream chat completion chunks"""
    import time

    created_timestamp = int(time.time())

    try:
        # Get agent instance
        agent = await get_agent()

        # Convert messages to LangChain format
        langchain_messages = []
        for msg in messages:
            langchain_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Stream the response
        async for chunk in agent.astream(
                {"messages": langchain_messages},
                stream_mode=["messages"],
                version="v2",
                config={"configurable": {"thread_id": completion_id}}
        ):
            if chunk["type"] == "messages":
                token, metadata = chunk["data"]
                if token.content:
                    # Create OpenAI-compatible chunk
                    chunk_data = ChatCompletionChunk(
                        id=completion_id,
                        created=created_timestamp,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {
                                "content": token.content,
                                "role": "assistant"
                            },
                            "finish_reason": None
                        }]
                    )

                    # Send chunk in SSE format
                    yield f"data: {chunk_data.model_dump_json(exclude_none=True)}\n\n"

        # Send final chunk
        final_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created_timestamp,
            model=model,
            choices=[{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        )
        yield f"data: {final_chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        # Send error chunk
        error_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }],
            "error": {
                "message": str(e),
                "type": "server_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


async def get_chat_completion(
        messages: List[ChatMessage],
        completion_id: str,
        model: str
) -> ChatCompletionResponse:
    """Get non-streaming chat completion"""
    import time

    created_timestamp = int(time.time())
    logger.info(f"Received non-streaming chat request: completion_id={completion_id}, model={model}, message_count={len(messages)}")

    try:
        # Get agent instance
        agent = await get_agent()

        # Convert messages to LangChain format
        langchain_messages = []
        for msg in messages:
            langchain_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Collect the full response
        full_content = ""
        async for chunk in agent.astream(
                {"messages": langchain_messages},
                stream_mode=["messages"],
                version="v2",
                config={"configurable": {"thread_id": completion_id}}
        ):
            if chunk["type"] == "messages":
                token, metadata = chunk["data"]
                if token.content:
                    full_content += token.content

        # Create response
        response = ChatCompletionResponse(
            id=completion_id,
            created=created_timestamp,
            model=model,
            choices=[ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=full_content),
                finish_reason="stop"
            )],
            usage=Usage(
                prompt_tokens=len("".join([msg.content for msg in messages])),
                completion_tokens=len(full_content),
                total_tokens=len("".join([msg.content for msg in messages])) + len(full_content)
            )
        )

        logger.info(f"Chat request completed: completion_id={completion_id}, response_length={len(full_content)}")
        return response

    except Exception as e:
        logger.error(f"Chat request failed: completion_id={completion_id}, error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions")
async def chat_completions(
        request: ChatCompletionRequest,
        http_request: Request
):
    """
    OpenAI-compatible chat completions endpoint

    Supports both streaming and non-streaming modes.
    """
    completion_id = generate_completion_id()

    if request.stream:
        # Streaming response
        return StreamingResponse(
            stream_chat_completion(
                messages=request.messages,
                completion_id=completion_id,
                model=request.model
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # Non-streaming response
        response = await get_chat_completion(
            messages=request.messages,
            completion_id=completion_id,
            model=request.model
        )
        return response

def start(host :str = "0.0.0.0", port: int = 8000):
    logger.info(f"Web server starting: host={host}, port={port}")
    uvicorn.run(app, host = host, port = port)

if __name__ == "__main__":
    start()