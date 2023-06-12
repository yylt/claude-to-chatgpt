# -*- coding:utf-8 -*- 
import httpx
import requests
import time
import json
import os
import uuid
from fastapi import Request
from claude_to_chatgpt.util import num_tokens_from_string
from claude_to_chatgpt.logger import logger
from claude_to_chatgpt.models import model_map
import poe 

role_map = {
    "system": "Human",
    "user": "Human",
    "assistant": "Assistant",
}

stop_reason_map = {
    "stop_sequence": "stop",
    "max_tokens": "length",
}


class ClaudeAdapter:
    def __init__(self,claude_api_key="", claude_base_url="https://api.anthropic.com"):
        self.claude_api_key = claude_api_key
        self.claude_base_url = claude_base_url

    def get_api_key(self, headers):
        auth_header = headers.get("authorization", None)
        if auth_header:
            return auth_header.split(" ")[1]
        else:
            return self.claude_api_key

    def convert_messages_to_prompt(self, messages):
        prompt = ""
        for message in messages:
            role = message["role"]
            content = message["content"]
            transformed_role = role_map[role]
            prompt += f"\n\n{transformed_role.capitalize()}: {content}"
        prompt += "\n\nAssistant: "
        return prompt

    def openai_to_claude_params(self, openai_params):
        model = model_map.get(openai_params["model"], "claude-v1.3-100k")
        messages = openai_params["messages"]

        prompt = self.convert_messages_to_prompt(messages)

        claude_params = {
            "model": model,
            "prompt": prompt,
            "max_tokens_to_sample": 100000 if model == "claude-v1.3-100k" else 9016,
        }

        if openai_params.get("max_tokens"):
            claude_params["max_tokens_to_sample"] = openai_params["max_tokens"]

        if openai_params.get("stop"):
            claude_params["stop_sequences"] = openai_params.get("stop")

        if openai_params.get("temperature"):
            claude_params["temperature"] = openai_params.get("temperature")

        if openai_params.get("stream"):
            claude_params["stream"] = True

        return claude_params

    def claude_to_chatgpt_response_stream(self, claude_response, prev_decoded_response):
        completion_tokens = num_tokens_from_string(claude_response["completion"])
        openai_response = {
            "id": f"chatcmpl-{str(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "gpt-3.5-turbo-0301",
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": completion_tokens,
                "total_tokens": completion_tokens,
            },
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": claude_response.get("completion", "").removeprefix(
                            prev_decoded_response.get("completion", "")
                        ),
                    },
                    "index": 0,
                    "finish_reason": stop_reason_map[claude_response.get("stop_reason")]
                    if claude_response.get("stop_reason")
                    else None,
                }
            ],
        }

        return openai_response

    def claude_to_chatgpt_response(self, claude_response):
        completion_tokens = num_tokens_from_string(claude_response["completion"])
        openai_response = {
            "id": f"chatcmpl-{str(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "gpt-3.5-turbo-0301",
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": completion_tokens,
                "total_tokens": completion_tokens,
            },
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": claude_response.get("completion", ""),
                    },
                    "index": 0,
                    "finish_reason": stop_reason_map[claude_response.get("stop_reason")]
                    if claude_response.get("stop_reason")
                    else None,
                }
            ],
        }

        return openai_response

    async def chat(self, request: Request):
        openai_params = await request.json()
        headers = request.headers
        claude_params = self.openai_to_claude_params(openai_params)
        api_key = self.get_api_key(headers)

        async with httpx.AsyncClient() as client:
            if not claude_params.get("stream", False):
                response = await client.post(
                    f"{self.claude_base_url}/v1/complete",
                    headers={
                        "x-api-key": api_key,
                        "content-type": "application/json",
                    },
                    json=claude_params,
                )
                if response.is_error:
                    raise Exception(f"Error: {response.status_code}")
                claude_response = response.json()
                openai_response = self.claude_to_chatgpt_response(claude_response)
                yield openai_response
            else:
                async with client.stream(
                    "POST",
                    f"{self.claude_base_url}/v1/complete",
                    headers={
                        "x-api-key": api_key,
                        "content-type": "application/json",
                    },
                    json=claude_params,
                ) as response:
                    if response.is_error:
                        raise Exception(f"Error: {response.status_code}")
                    prev_decoded_line = {}
                    async for line in response.aiter_lines():
                        if line:
                            if line == "data: [DONE]":
                                yield "[DONE]"
                                break
                            stripped_line = line.lstrip("data:")
                            if stripped_line:
                                try:
                                    decoded_line = json.loads(stripped_line)
                                    # yield decoded_line
                                    openai_response = (
                                        self.claude_to_chatgpt_response_stream(
                                            decoded_line, prev_decoded_line
                                        )
                                    )
                                    prev_decoded_line = decoded_line
                                    yield openai_response
                                except json.JSONDecodeError as e:
                                    logger.debug(
                                        f"Error decoding JSON: {e}"
                                    )  # Debug output
                                    logger.debug(
                                        f"Failed to decode line: {stripped_line}"
                                    )  # Debug output

class ClaudeSlackAdapter:
    def __init__(self, channelid="",access_token="",claude_slack_url=""):
        self.channel_id = channelid
        self.access_token = access_token
        self.claude_base_url = claude_slack_url

    def convert_messages_to_prompt(self, messages):
        return messages[len(messages)-1]["content"]

    def openai_to_claude_params(self, openai_params):
        model = model_map.get(openai_params["model"], "claude-v1.3-100k")
        messages = openai_params["messages"]

        prompt = self.convert_messages_to_prompt(messages)

        claude_params = {
            "action": "next",
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "role": "user",
                    "author": {
                        "role": "user"
                    },
                    "content": {
                        "content_type": "text",
                        "parts": [
                            prompt
                        ]
                    }
                }
            ],
            "parent_message_id": str(uuid.uuid4()),
            "model": model,
        }
        if openai_params.get("stream"):
            claude_params["stream"] = True
        return claude_params

    
    def chatgpt_response(self, decoded_line, prev_decoded_line,model="gpt-3.5-turbo"):
        content = decoded_line.removeprefix(prev_decoded_line)
        length = len(content)
        return  {
            "id": f"chatcmpl-{str(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": length,
                "total_tokens": length,
            },
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": content,
                    },
                    "index": 0,
                }
            ],
        }
    
    def claude_to_chatgpt_response(self, claude_response, stream=False, model="gpt-3.5-turbo"):
        prev_decoded_line = ""
        for line in claude_response.iter_lines():
            if not line or line is None:
                continue
            if line.find(b'[DONE]') >0:
                if stream is False:
                    try:
                        json_line = json.loads(stripped_line)
                        decoded_line = json_line["message"]["content"]["parts"][0]
                        # yield decoded_line
                        yield (self.chatgpt_response(decoded_line, "",model))
                    except json.JSONDecodeError as e:
                        logger.info(
                            f"Error decoding JSON: {e}"
                        ) 
                yield "[DONE]"
                break
            
            stripped_line = line.removeprefix(b'data: ')
            if stream is False:
                continue
            try:
                json_line = json.loads(stripped_line)
                decoded_line = json_line["message"]["content"]["parts"][0]
                # yield decoded_line
                openai_response = (self.chatgpt_response(decoded_line, prev_decoded_line,model))
                prev_decoded_line = decoded_line
                yield openai_response
            except json.JSONDecodeError as e:
                logger.info(
                    f"Error decoding JSON: {e}"
                ) 

    async def chat(self, request: Request):
        openai_params = await request.json()
        claude_params = self.openai_to_claude_params(openai_params)

        response = requests.post(
                f"{self.claude_base_url}/backend-api/conversation",
                headers={
                    'Authorization': f'Bearer {self.channel_id}@{self.access_token}',
                    "content-type": "application/json",
                },
                json=claude_params,
                timeout=60,
            )
        response.raise_for_status()
        resp = self.claude_to_chatgpt_response(response,
                                              openai_params.get("stream", False),
                                              openai_params.get("model"))
        yield resp
        

class PoeAdapter:
    def __init__(self, poe_token, proxy, model):
        self.client = poe.Client(poe_token, proxy=proxy)
        self.model = model

    def convert_messages_to_prompt(self, messages):
        return messages[len(messages)-1]["content"]

    def openai_to_poe_params(self, openai_params):
        messages = openai_params["messages"]
        prompt = self.convert_messages_to_prompt(messages)

        return prompt

    def chatgpt_response(self, decoded_line, prev_decoded_line,model="gpt-3.5-turbo"):
        content = decoded_line.removeprefix(prev_decoded_line)
        length = len(content)
        return  {
            "id": f"chatcmpl-{str(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": length,
                "total_tokens": length,
            },
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": content,
                    },
                    "index": 0,
                }
            ],
        }
    
    def poe_to_chatgpt_response(self, response, stream=False, model="gpt-3.5-turbo"):
        chunk = response.get("text_new", None)
        if chunk is None:
            yield "[DONE]"
            return 
        yield (self.chatgpt_response(chunk, "",model))
        

    async def chat(self, request: Request):
        openai_params = await request.json()
        prompt = self.openai_to_poe_params(openai_params)
        for chunk in self.client.send_message(self.model, prompt, with_chat_break=False):
            #print(chunk["text_new"], end="", flush=True)
            resp = self.poe_to_chatgpt_response(chunk,
                                                openai_params.get("stream", False),
                                                openai_params.get("model"))
            yield resp
        yield "[DONE]"
