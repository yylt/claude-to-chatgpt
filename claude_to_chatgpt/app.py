# -*- coding:utf-8 -*- 
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from claude_to_chatgpt.adapter import ClaudeAdapter, ClaudeSlackAdapter
import json
import os
from claude_to_chatgpt.logger import logger
from claude_to_chatgpt.models import models_list

CLAUDE_BASE_URL = os.getenv("CLAUDE_BASE_URL", "https://api.anthropic.com")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", None)

CLAUDE_SLACK_URL = os.getenv("CLAUDE_SLACK_URL", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")
SLACK_ACCESS_TOKEN = os.getenv("SLACK_ACCESS_TOKEN", "")

LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
PORT = os.getenv("PORT", 8000)
HOST = os.getenv("HOST", "0.0.0.0")


#adapter = ClaudeAdapter(CLAUDE_API_KEY, CLAUDE_BASE_URL)
slackadapter = ClaudeSlackAdapter(SLACK_CHANNEL,SLACK_ACCESS_TOKEN,CLAUDE_SLACK_URL)

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
    if openai_params.get("stream", False):

        async def generate():
            async for response in slackadapter.chat(request):
                for resp in list(response):
                    #print(resp)
                    yield f"data: {json.dumps(resp)}\n\n"
                break

        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        openai_response = None
        response = slackadapter.chat(request)
        openai_response = await response.__anext__()
        return JSONResponse(content=openai_response)


@app.route("/v1/models", methods=["GET"])
async def models(request: Request):
    # return a dict with key "object" and "data", "object" value is "list", "data" values is models list
    return JSONResponse(content={"object": "list", "data": models_list})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=HOST, port=PORT, log_level=LOG_LEVEL)
