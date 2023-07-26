# -*- coding:utf-8 -*- 
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from claude_to_chatgpt.adapter import ClaudeAdapter, ClaudeSlackAdapter, PoeAdapter, claude2Adapter
import json
import os
from claude_to_chatgpt.logger import logger
from claude_to_chatgpt.models import models_list

CLAUDE_BASE_URL = os.getenv("CLAUDE_BASE_URL", "https://api.anthropic.com")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", None)
CLAUDE2_COOKIE = os.getenv("CLAUDE2_COOKIE", None)
CLAUDE2_CHATID = os.getenv("CLAUDE2_CHATID", None)
CLAUDE2_ORGID = os.getenv("CLAUDE2_ORGID", None)

CLAUDE_SLACK_URL = os.getenv("CLAUDE_SLACK_URL", None)
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", None)
SLACK_ACCESS_TOKEN = os.getenv("SLACK_ACCESS_TOKEN", None)

POE_TOKEN = os.getenv("POE_TOKEN", None)
POE_PROXY = os.getenv("POE_PROXY", None)
POE_GPT3_MODEL = os.getenv("POE_GPT3_MODEL", "chinchilla") 
POE_GPT4_MODEL = os.getenv("POE_GPT4_MODEL", "a2_2") 
"""
{
  "capybara": "Sage",
  "a2": "Claude-instant",
  "chinchilla": "ChatGPT-3.5",
  "nutria": "Dragonfly",
  "a2_100k": "Claude-instant-100k",
  "beaver": "GPT-4",
  "a2_2": "Claude+"
}
"""

MODEL = os.getenv("MODEL", "poe")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
PORT = os.getenv("PORT", 8000)
HOST = os.getenv("HOST", "0.0.0.0")

# default is poeadapter
if MODEL=="poe": 
    adapter = PoeAdapter(POE_TOKEN, POE_PROXY, POE_GPT3_MODEL, POE_GPT4_MODEL)
elif MODEL=="slack":
    adapter = ClaudeSlackAdapter(SLACK_CHANNEL,SLACK_ACCESS_TOKEN,CLAUDE_SLACK_URL)
elif MODEL=="claude2":
    adapter = claude2Adapter(CLAUDE2_COOKIE, CLAUDE2_CHATID, CLAUDE2_ORGID)
else:
    adapter =  ClaudeAdapter(CLAUDE_API_KEY, CLAUDE_BASE_URL)
    
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods, including OPTIONS
    allow_headers=["*"],
)


@app.api_route(
    "/v1/chat/completions",
    methods=["POST", "OPTIONS"],
)
async def chat(request: Request):
    openai_params = await request.json()
    stream=openai_params.get("stream")
    if stream is None:
        openai_params["stream"]=True
    if openai_params.get("stream", False):
        async def generate():
            async for response in adapter.chat(request):
                #print("response: ",response)
                if isinstance(response, str) and response.find("[DONE]")>-1:
                    yield "data: [DONE]\n\n"
                    break
                yield f"data: {json.dumps(response)}\n\n"
        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        openai_response = None
        response = adapter.chat(request)
        openai_response = await response.__anext__()
        return JSONResponse(content=openai_response)


@app.route("/v1/models", methods=["GET"])
async def models(request: Request):
    # return a dict with key "object" and "data", "object" value is "list", "data" values is models list
    return JSONResponse(content={"object": "list", "data": models_list})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=HOST, port=PORT, log_level=LOG_LEVEL)
