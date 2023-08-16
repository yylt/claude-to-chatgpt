# -*- coding:utf-8 -*- 
import httpx
import requests
import time
import json
import uuid
from fastapi import Request
from claude_to_chatgpt.util import num_tokens_from_string
from claude_to_chatgpt.logger import logger
from claude_to_chatgpt.models import model_map
import poe 
import claude

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

        async with httpx.AsyncClient(timeout=60.0) as client:
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
        model = model_map.get(openai_params["model"], "gpt-3.5-turbo")
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
        claude_params["stream"] = openai_params.get("stream", True)
        return claude_params

    
    def chatgpt_response(self, decoded_line, prev_decoded_line, t, model):
        content = decoded_line[len(prev_decoded_line):]
        length = len(content)
        
        return  {
            "id": f"chatcmpl-{str(t)}",
            "object": "chat.completion",
            "created": int(t),
            "model": model,
            "usage": {
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
   
    async def chat(self, request: Request):
        openai_params = await request.json()
        claude_params = self.openai_to_claude_params(openai_params)
        t=time.time()
        try:
            response = requests.post(
                    f"{self.claude_base_url}/backend-api/conversation",
                    headers={
                        'Authorization': f'Bearer {self.channel_id}@{self.access_token}',
                        "content-type": "application/json",
                    },
                    json=claude_params,
                    timeout=10,
                    stream=True,
                )
            response.raise_for_status()
        except Exception as e:
            print("slack server failed: ",e)
            yield ( finish(t,openai_params.get("model")) )
            return

        prev_decoded_line = ""
        for line in response.iter_lines():
            if not line or line is None:
                continue
            if not line.startswith(b'data:'):
                continue
            stripped_line = line.removeprefix(b'data: ')
            if not stripped_line:
                continue
            if stripped_line.find(b'[DONE]')>-1:
                yield ( finish(t,openai_params.get("model")) )
                break
            try:
                json_line = json.loads(stripped_line)
                decoded_line = json_line["message"]["content"]["parts"][0]
                # yield decoded_line
                openai_response = self.chatgpt_response(decoded_line, prev_decoded_line, t, claude_params.get("model"))
                prev_decoded_line = decoded_line
                yield ( openai_response )
            except Exception as e:
                print(f"req slack failed: {e}") 
                yield ( finish(t,openai_params.get("model")) )
                
class PoeAdapter:
    def __init__(self, poe_token, proxy, model3, model4):
        self.client = poe.Client(poe_token, proxy=proxy)
        self.model3 = model3
        self.model4 = model4

    def convert_messages_to_prompt(self, messages):
        return messages[len(messages)-1]["content"]

    def openai_to_poe_params(self, openai_params):
        messages = openai_params["messages"]
        prompt = self.convert_messages_to_prompt(messages)

        return prompt

    def chatgpt_response(self, decoded_line, prev_decoded_line, t, model="gpt-3.5-turbo"):
        content = decoded_line[len(prev_decoded_line):]
        length = len(content)
        return  {
            "id": f"chatcmpl-{str(t)}",
            "object": "chat.completion",
            "created": int(t),
            "model": model,
            "usage": {
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
    
    async def chat(self, request: Request):
        openai_params = await request.json()
        prompt = self.openai_to_poe_params(openai_params)
        t = time.time()
        if openai_params.get("stream", False) == False:
            yield ( finish(t,openai_params.get("model")) )
        omodel = openai_params.get("model", "gpt-3.5-turbo")
        model = self.model3
        if omodel.startswith("gpt-4"):
            model =self.model4
        try:
            for resp in self.client.send_message(model, prompt, with_chat_break=True):
                chunk = resp.get("text_new", None)
                if chunk is None:
                    yield ( finish(t,openai_params.get("model")) )
                    return 
                r = self.chatgpt_response(chunk, "", t, openai_params.get("model"))
                yield ( r )
            yield ( finish(t,openai_params.get("model")) )
        except Exception as e:
            print(f"req poe.com failed: {e}")
            yield ( finish(t,openai_params.get("model")) )


class claude2Adapter:
    def __init__(self, cookie, chatid, orgid=None):
        self.client = claude.Client(cookie=cookie,organization=orgid)
        self.conversation_id = chatid

    def convert_messages_to_prompt(self, messages):
        return messages[len(messages)-1]["content"]

    def openai_to_params(self, openai_params):
        messages = openai_params["messages"]
        prompt = self.convert_messages_to_prompt(messages)

        return prompt

    def chatgpt_response(self, decoded_line, prev_decoded_line, t, model="gpt-3.5-turbo"):
        content = decoded_line[len(prev_decoded_line):]
        length = len(content)
        return  {
            "id": f"chatcmpl-{str(t)}",
            "object": "chat.completion",
            "created": int(t),
            "model": model,
            "usage": {
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
    
    async def chat(self, request: Request):
        openai_params = await request.json()
        prompt = self.openai_to_params(openai_params)
        t = time.time()
        if openai_params.get("stream", False) == False:
            yield ( finish(t,openai_params.get("model")) )
        try:
            pre_completion = ""
            # response = self.client.send_message(prompt, self.conversation_id)
            # print(f"prompt: {prompt}, response: {response}")
            
            # for line in response.iter_lines():
            async for line in self.client.send_message(prompt, self.conversation_id):
                # print(f"prompt: {prompt}, response: {line}")
                # if line.startswith(b'data:'):
                #     json_obj = json.loads(line[6:])
                #     completion = json_obj.get('completion')
                #     if completion is None:
                #         continue
                for completion in line:                    
                    r = self.chatgpt_response(completion, pre_completion,t, openai_params.get("model"))
                    yield ( r )
            yield ( finish(t,openai_params.get("model")) )
        except Exception as e:
            print(f"req claude2 failed: {e}")
            yield ( finish(t,openai_params.get("model")) )


# TBD
class MerlinAdapter:
    chat="chat/merlin-actions?customJWT=true"
    status="status"
    def __init__(self, merlinURL, users, passwords, googlekey):
        self.client = poe.Client(poe_token, proxy=proxy)
        self.model = model

    def convert_messages_to_prompt(self, messages):
        return messages[len(messages)-1]["content"]

    def openai_to_poe_params(self, openai_params):
        messages = openai_params["messages"]
        prompt = self.convert_messages_to_prompt(messages)

        return prompt

    def chatgpt_response(self, decoded_line, prev_decoded_line, t, model="gpt-3.5-turbo"):
        content = decoded_line.removeprefix(prev_decoded_line)
        length = len(content)
        
        return  {
            "id": f"chatcmpl-{str(t)}",
            "object": "chat.completion",
            "created": int(t),
            "model": model,
            "usage": {
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
    
    async def chat(self, request: Request):
        openai_params = await request.json()
        prompt = self.openai_to_poe_params(openai_params)
        t = time.time()
        if openai_params.get("stream", False)==False:
            yield ( finish(t,openai_params.get("model")) )
        for resp in self.client.send_message(self.model, prompt, with_chat_break=True):
            chunk = resp.get("text_new", None)
            if chunk is None:
                yield ( finish(t,openai_params.get("model")) )
                return 
            r = self.chatgpt_response(chunk, "", t, openai_params.get("model"))
            yield ( r )
        yield ( finish(t,openai_params.get("model")) )


def finish(t,model):
    return {
        "id": f"chatcmpl-{str(t)}",
        "object": "chat.completion",
        "created": int(t),
        "model": model,
        "choices": [
            {
                "finish_reason": "done",
                "index": 0,
            }
        ],
    }