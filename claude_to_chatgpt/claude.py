# -*- coding:utf-8 -*- 
#import requests
import json
import os
import uuid
import httpx
import ssl
import random
from curl_cffi import requests
import tls_client as requests_tls
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.ssl_ import create_urllib3_context

ORIGIN_CIPHERS = ('ECDH+AESGCM:DH+AESGCM:ECDH+AES256')

class SSLFactory:
    def __init__(self):
        self.ciphers = ORIGIN_CIPHERS.split(":")
 
    def __call__(self) -> ssl.SSLContext:
        random.shuffle(self.ciphers)
        ciphers = ":".join(self.ciphers)
        ciphers = ciphers + ":!aNULL:!eNULL:!MD5"
        context = ssl.create_default_context()
        context.set_ciphers(ciphers)
        return context
 
class DESAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        """
        A TransportAdapter that re-enables 3DES support in Requests.
        """      
        CIPHERS = ORIGIN_CIPHERS.split(':')
        random.shuffle(CIPHERS)
        CIPHERS = ':'.join(CIPHERS)
        self.CIPHERS = CIPHERS + ':!aNULL:!eNULL:!MD5'
        print(f"{self.CIPHERS}")
        super().__init__(*args, **kwargs)
 
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers=self.CIPHERS)
        kwargs['ssl_context'] = context
        return super(DESAdapter, self).init_poolmanager(*args, **kwargs)
 
    def proxy_manager_for(self, *args, **kwargs):
        context = create_urllib3_context(ciphers=self.CIPHERS)
        kwargs['ssl_context'] = context
        return super(DESAdapter, self).proxy_manager_for(*args, **kwargs)
 
class Client:
  sendurl = "https://claude.ai/api/append_message"

  headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36 Edg/92.0.902.67',
    'Accept': 'text/event-stream',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://claude.ai/chats',
    'Content-Type': 'application/json',
    'Origin': 'https://claude.ai',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'TE': 'trailers'
  }

  def __init__(self, cookie, organization):
    self.cookie = cookie
    #self.session = requests_tls.Session(client_identifier="chrome_103")
    #self.asession = requests.AsyncSession()
    self.session = requests.Session()
    sslgen = SSLFactory()
    self.client = httpx.AsyncClient(timeout=20.0, verify=sslgen())

    if organization is not None:
        self.organization_id = organization
    else:
        self.organization_id = self.get_organization_id()

  def get_organization_id(self):
    url = "https://claude.ai/api/organizations"

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://claude.ai/chats',
        'Content-Type': 'application/json',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Cookie': f'{self.cookie}'
    }

    response = self.session.get(url, headers=headers)
    res = json.loads(response.text)
    uuid = res[0]['uuid']

    return uuid

  def get_content_type(self, file_path):
    # Function to determine content type based on file extension
    extension = os.path.splitext(file_path)[-1].lower()
    if extension == '.pdf':
      return 'application/pdf'
    elif extension == '.txt':
      return 'text/plain'
    elif extension == '.csv':
      return 'text/csv'
    # Add more content types as needed for other file types
    else:
      return 'application/octet-stream'

  # Lists all the conversations you had with Claude
  def list_all_conversations(self):
    url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations"

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://claude.ai/chats',
        'Content-Type': 'application/json',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Cookie': f'{self.cookie}'
    }

    response = self.session.get(url, headers=headers)
    conversations = response.json()

    # Returns all conversation information in a list
    if response.status_code == 200:
      return conversations
    else:
      print(f"Error: {response.status_code} - {response.text}")

  # Send Message to Claude
  async def send_message(self, prompt, conversation_id, attachment=None):

    # Upload attachment if provided
    attachments = []
    if attachment:
      attachment_response = self.upload_attachment(attachment)
      if attachment_response:
        attachments = [attachment_response]
      else:
        yield {"Error: Invalid file format. Please try again."}

    # Ensure attachments is an empty list when no attachment is provided
    if not attachment:
      attachments = []

    payload = json.dumps({
      "completion": {
        "prompt": f"{prompt}",
        "timezone": "Asia/Shanghai",
        "model": "claude-2"
      },
      "organization_uuid": f"{self.organization_id}",
      "conversation_uuid": f"{conversation_id}",
      "text": f"{prompt}",
      "attachments": attachments
    })
    self.headers['Cookie']= self.cookie

    # Stop streaming by returning None
    # async with self.client.stream("POST", self.sendurl, headers = self.headers, data=payload) as resp:
    #     print(resp)
    #     async for chunk in resp.aiter_lines():
    #         yield chunk
 
    # se = requests_tls.Session(client_identifier='chrome_103')
    # response = se.post(self.sendurl, headers=self.headers, data=payload)
    # print(f"code: {response.status_code}")

    # for i in range(20):
    #   self.session.mount('', DESAdapter())
    #   response = self.session.post(self.sendurl, headers=self.headers, data=payload, stream=True)
    #   print(f"code: {response.content}")
    #   if response.status_code // 100 == 2 :
    #     return response
    # return response

    content = []

    async with requests.AsyncSession() as s:
        await s.post(self.sendurl, headers=self.headers, data=payload, impersonate="chrome101",
                        content_callback=lambda chunk: self.chunk_callback(chunk, content),
                        timeout=120)
    yield content
    #print("".join(response_content))

  def chunk_callback(self, chunk, content, *args, **kwargs):
      #print(chunk)
      njsondata = chunk.decode("utf-8").split('\n\n')
      for line in njsondata:
          if line.startswith('data:'):
            json_obj = json.loads(line[6:])
            completion = json_obj.get('completion')
            if completion is None:
                continue
            content.append(completion)

      
  # Deletes the conversation
  def delete_conversation(self, conversation_id):
    url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations/{conversation_id}"

    payload = json.dumps(f"{conversation_id}")
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Content-Type': 'application/json',
        'Content-Length': '38',
        'Referer': 'https://claude.ai/chats',
        'Origin': 'https://claude.ai',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Cookie': f'{self.cookie}',
        'TE': 'trailers'
    }

    response = requests.request("DELETE", url, headers=headers, data=payload, impersonate="chrome112")

    # Returns True if deleted or False if any error in deleting
    if response.status_code == 204:
      return True
    else:
      return False

  # Returns all the messages in conversation
  def chat_conversation_history(self, conversation_id):
    url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations/{conversation_id}"

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://claude.ai/chats',
        'Content-Type': 'application/json',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Cookie': f'{self.cookie}'
    }

    response = requests.request("GET", url, headers=headers, impersonate="chrome112")
    print(type(response))

    # List all the conversations in JSON
    return response.json()

  def generate_uuid(self):
    random_uuid = uuid.uuid4()
    random_uuid_str = str(random_uuid)
    formatted_uuid = f"{random_uuid_str[0:8]}-{random_uuid_str[9:13]}-{random_uuid_str[14:18]}-{random_uuid_str[19:23]}-{random_uuid_str[24:]}"
    return formatted_uuid

  def create_new_chat(self):
    url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations"
    uuid = self.generate_uuid()

    payload = json.dumps({"uuid": uuid, "name": ""})
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://claude.ai/chats',
        'Content-Type': 'application/json',
        'Origin': 'https://claude.ai',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Cookie': self.cookie,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'TE': 'trailers'
    }

    response = requests.request("POST", url, headers=headers, data=payload, impersonate="chrome112")

    # Returns JSON of the newly created conversation information
    return response.json()

  # Resets all the conversations
  def reset_all(self):
    conversations = self.list_all_conversations()

    for conversation in conversations:
      conversation_id = conversation['uuid']
      delete_id = self.delete_conversation(conversation_id)

    return True

  def upload_attachment(self, file_path):
    url = 'https://claude.ai/api/convert_document'
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://claude.ai/chats',
        'Origin': 'https://claude.ai',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Cookie': f'{self.cookie}',
        'TE': 'trailers'
    }

    file_name = os.path.basename(file_path)
    content_type = self.get_content_type(file_path)

    files = {
        'file': (file_name, open(file_path, 'rb'), content_type),
        'orgUuid': (None, self.organization_id)
    }

    response = requests.post(url, headers=headers, files=files, impersonate="chrome112")
    if response.status_code == 200:
      return response.json()
    else:
      return False
      

    
  # Renames the chat conversation title
  def rename_chat(self, title, conversation_id):
    url = "https://claude.ai/api/rename_chat"

    payload = json.dumps({
        "organization_uuid": f"{self.organization_id}",
        "conversation_uuid": f"{conversation_id}",
        "title": f"{title}"
    })
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Content-Type': 'application/json',
        'Referer': 'https://claude.ai/chats',
        'Origin': 'https://claude.ai',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive',
        'Cookie': f'{self.cookie}',
        'TE': 'trailers'
    }

    response = requests.request("POST", url, headers=headers, data=payload, impersonate="chrome112")

    if response.status_code == 200:
      return True
    else:
      return False
      