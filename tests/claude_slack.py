import json
import uuid
import requests


def interact_with_server(channel_id, access_token, prompt, conversation_id=None):
    payload = {
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
        "conversation_id": conversation_id,
        "parent_message_id": str(uuid.uuid4()),
        "model": "claude-unknown-version"
    }

    headers = {
        'Authorization': f'Bearer {channel_id}@{access_token}',
        'Content-Type': 'application/json'
    }

    response = requests.post("http://your_server_ip:5000/backend-api/conversation", headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    for line in response.iter_lines():
        if not line or line is None:
            continue
        if "data: " in line:
            line = line[6:]
        if "[DONE]" in line:
            break

        try:
            line = json.loads(line)
        except json.decoder.JSONDecodeError:
            continue

        conversation_id = line["conversation_id"]
        message = line["message"]["content"]["parts"][0]
        yield (conversation_id, message)

# Example usage
channel_id = 'C0XXXXXXX' # From Step 3
access_token = 'xxxxxxx' # From Step 3
conversation_id = None

# First call
for conversation_id, message in interact_with_server(channel_id, access_token, "Can you say some emojis?", conversation_id):
    print(f"Received message: {message}")