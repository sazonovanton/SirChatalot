# Description: Chats processing class

from chatutils.misc import setup_logging, read_config, leave_only_text
from chatutils.datatypes import FunctionResponse, Message

config = read_config('./data/.config')
logger = setup_logging(logger_name='SirChatalot-Engines', log_level=config.get('Logging', 'LogLevel', fallback='WARNING'))

import hashlib
import tiktoken
import asyncio
import json
import configparser

######## OpenAI Engine ########

class OpenAIEngine:
    def __init__(self):
        '''
        Initialize OpenAI API 
        '''
        self.name = 'OpenAI'
        from openai import AsyncOpenAI
        import openai 
        self.openai = openai

        self.config = configparser.ConfigParser()
        self.config.read('./data/.config', encoding='utf-8')  

        # check if alternative API base is used
        self.base_url = None
        if self.config.has_option("OpenAI", "APIBase"):
            if str(self.config.get("OpenAI", "APIBase")).lower() not in ['default', '', 'none', 'false']:
                self.base_url = self.config.get("OpenAI", "APIBase")
            else:
                self.base_url = None

        # Set up the API 
        self.client = AsyncOpenAI(
            api_key=self.config.get("OpenAI", "SecretKey"),
            base_url=self.base_url,
        )
        self.text_init() 

        # Get the encoding for the model
        self.model_encoding = None
        self.fallback_enc_base = 'cl100k_base'
        try:
            self.model_encoding = tiktoken.encoding_for_model(self.model.split('/')[-1])
        except KeyError:
            logger.warning(f"Could not get encoding for model `{self.model.split('/')[-1]}`, falling back to encoding for `{self.fallback_enc_base}`")
            self.model_encoding = tiktoken.get_encoding(self.fallback_enc_base)

        logger.info('OpenAI Engine was initialized')

    def text_init(self):
        '''
        Initialize text generation
        '''
        self.model = self.config.get("OpenAI", "ChatModel", fallback="gpt-4o-mini")
        self.model_completion_price = self.config.getfloat("OpenAI", "ChatModelCompletionPrice", fallback=0)
        self.model_prompt_price = self.config.getfloat("OpenAI", "ChatModelPromptPrice", fallback=0)
        self.temperature = self.config.getfloat("OpenAI", "Temperature", fallback=0.67)
        self.max_tokens = self.config.getint("OpenAI", "MaxTokens", fallback=3997)
        self.end_user_id = self.config.getboolean("OpenAI", "EndUserID", fallback=False)
        self.system_message = self.config.get("OpenAI", "SystemMessage", fallback="You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages.")
        self.moderation = self.config.getboolean("OpenAI", "Moderation", fallback=False)
        self.max_chat_length = self.config.getint("OpenAI", "MaxSessionLength", fallback=None)
        self.log_chats = self.config.getboolean("Logging", "LogChats", fallback=False)
        self.summarize_too_long = self.config.getboolean("OpenAI", "SummarizeTooLong", fallback=False)
        self.requested_tokens = self.config.getint("OpenAI", "ResponseMaxTokens", fallback=None)

        self.vision = self.config.getboolean("OpenAI", "Vision", fallback=False)
        self.function_calling = self.config.getboolean("OpenAI", "FunctionCalling", fallback=False)
        if self.vision:
            self.image_size = self.config.getint("OpenAI", "ImageSize", fallback=512)
            self.delete_image_after_chat = self.config.getboolean("OpenAI", "DeleteImageAfterAnswer", fallback=False)
            self.image_description = self.config.getboolean("OpenAI", "ImageDescriptionOnDelete", fallback=False)
        if self.function_calling:
            self.function_calling_tools = None
        else:
            self.function_calling_tools = self.openai.NOT_GIVEN

        if self.max_chat_length is not None:
            print('Max chat length:', self.max_chat_length)
            print('-- Max chat length is states a length of chat session. It can be changed in the self.config file.\n')
        if self.moderation:
            print('Moderation is enabled')
            print('-- Moderation is used to check if content complies with OpenAI usage policies. It can be changed in the self.config file.')
            print('-- Learn more: https://platform.openai.com/docs/guides/moderation/overview\n')
        if self.vision:
            print('Vision is enabled')
            print('-- Vision is used to describe images and delete them from chat history. It can be changed in the self.config file.')
            print('-- Learn more: https://platform.openai.com/docs/guides/vision/overview\n')
        if self.function_calling:
            print('Function calling is enabled')
            print('-- Function calling is used to call functions from OpenAI API. It can be changed in the self.config file.')
            print('-- Learn more: https://platform.openai.com/docs/guides/function-calling\n')
        
    async def detect_function_called(self, response):
        '''
        Detect if function was called in response
        Learn more: https://platform.openai.com/docs/guides/function-calling
        Input:
            * response - response from GPT
        Output:
            * FunctionResponse - response with function called
        '''
        response_message = None
        tool_id = None
        try:
            logger.debug(f'Detecting function called in response: "{response}"')
            if response is None:
                return None
            if not self.function_calling:
                return response
            if self.function_calling_tools is None:
                return response
            if not response.choices[0].finish_reason == 'function_call':
                return response
            
            tool_calls = response_message.tool_calls

            function_response = FunctionResponse()
            function_response.function_name=tool_calls[0].function.name
            function_response.function_args=json.loads(tool_calls[0].function.arguments)
            function_response.tool_id=tool_id

            return function_response
        except Exception as e:
            logger.error(f'Could not detect tool called: {e}')
            raise Exception('Could not detect tool called')
        
    async def revise_messages(self, messages):
        '''
        Format messages for OpenAI API
        From: [Message, Message, Message,...]
        To: [{"role": "string", "content": "string"}, ...]
        Also delete message with role "system"
        '''
        try:
            revised_messages = []
            for message in messages:
                role = message.role
                content = message.content
                if role == 'function':
                    revised_messages.append({"role": role, 
                                             "name": content.function_name, 
                                             "content": content.content})
                else:
                    revised_messages.append({"role": role, "content": content})
            return revised_messages
        except Exception as e:
            logger.exception('Could not revise messages for OpenAI API')
            raise Exception('Could not revise messages for OpenAI API')
        
    async def chat(self, id=0, messages=None):
        '''
        Chat with GPT
        Input id of user and message
        Input:
          * id - id of user
          * messages = [Message, Message, Message,...]
          * attempt - attempt to send message
        Output:
          * Message - response from GPT
        If messages tokens are more than 80% of max_tokens, it will be trimmed. 20% of tokens are left for response.
        '''
        if messages is None:
            return None
        
        new_message = Message()

        if self.moderation:
            messages[-1].moderated = True
            if await self.moderation_pass(messages[-1], id) == False:
                messages[-1].moderated = False
                new_message.error = 'ModerationError'
                return new_message
            
        try:
            new_message.model = {
                'name': self.model,
                'prompt_price': self.model_prompt_price,
                'completion_price': self.model_completion_price
            }
            messages_tokens = await self.count_tokens(messages)
            if messages_tokens is None:
                messages_tokens = 0

            user_id = str(hashlib.sha1(str(id).encode("utf-8")).hexdigest()) if self.end_user_id else self.openai.NOT_GIVEN
            response = await self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature, 
                    max_tokens=self.requested_tokens,
                    messages=await self.revise_messages(messages),
                    user=user_id,
                    tools=self.function_calling_tools,
                    tool_choice="auto" if self.function_calling else self.openai.NOT_GIVEN
                )
            
            response = await self.detect_function_called(response)
            new_message.tokens = {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens
            }
            new_message.finish_reason = response.choices[0].finish_reason
            if response is not None:
                if type(response) == FunctionResponse:
                    new_message.content = response
                    new_message.role = 'function'
                    new_message.content_type = 'function'
                else:
                    new_message.content = response.choices[0].message.content
                    new_message.role = 'assistant'
                
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI RateLimitError: {e}')
            new_message.error = 'RateLimitError'
        except self.openai.BadRequestError as e:
            if 'does not exist' in str(e):
                logger.error(f'Invalid model error for model {self.model}')
                new_message.error = 'InvalidModel'
            else:
                logger.error(f'Invalid request error: {e}')
                new_message.error = 'BadRequestError'
        except Exception as e:
            logger.exception('Could not get response from GPT')
            new_message.error = f'UnknownError'
            new_message.misc = str(e)
        finally:
            return new_message

    async def chat_summary(self, messages, maxtokens=420):
        '''
        Summarize chat history
        Input messages and short flag (states that summary should be in one sentence)
        Returns message object
        '''
        try:
            if messages is None or len(messages) == 0:
                return None
            summary_message = Message()
            
            if messages[0].role == 'system':
                messages[0].content = "Summaraize current chat contents for the future use."

            user_id = str(hashlib.sha1(str(id).encode("utf-8")).hexdigest()) if self.end_user_id else self.openai.NOT_GIVEN
            response = await self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature, 
                    max_tokens=maxtokens,
                    messages=await self.revise_messages(messages),
                    user=user_id
                )
            
            summary_message.tokens = {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens
            }

            summary_message.finish_reason = response.choices[0].finish_reason
            summary_message.content = f"<Previous conversation summary:>\n{response.choices[0].message.content}"
            summary_message.role = 'assistant'

            return summary_message
        except Exception as e:
            logger.exception('Could not summarize chat history')
            summary_message.error = 'SummaryError'
            summary_message.misc = str(e)
            return summary_message
        
    async def moderation_pass(self, message=None, id=0):
        try:
            if message is None or len(message) == 0:
                return None
            
            if self.vision:
                message, trimmed = await leave_only_text(message)

            response = await self.client.moderations.create(
                input=[message.content],
                model='text-moderation-stable',
                )
            output = response.results[0]

            if output.flagged:
                categories = output.categories
                logger.warning(f'Message from user {id} was flagged ({categories})')
                with open('./data/moderation.txt', 'a') as f:
                    f.write(f'{id}: ({categories})\n{message.content}\n---\n\n')
                return False
            return True
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI Moderation RateLimitError: {e}')
            return None
        except self.openai.InternalServerError as e:
            logger.error(f'OpenAI Moderation InternalServerError: {e}')
            return None
        except Exception as e:
            logger.exception('Could not moderate message')
            return None

    async def count_tokens(self, messages):
        '''
        Count tokens in messages via tiktoken
        '''
        try:
            # If messages empty
            if messages is None:
                logger.debug('Messages are empty')
                return None
            if len(messages) == 0:
                return 0
            # Count the number of tokens
            tokens = 0
            for message in messages:
                # Check if there is images in message and leave only text
                if self.vision:
                    message, trimmed = await leave_only_text(message, logger=logger)
                tokens += len(self.model_encoding.encode(message.content))
            logger.debug(f'Messages were counted for tokens: {tokens}')
            return tokens
        except Exception as e:
            logger.error(f'Counting tokens failed: {e}')
            return None
        
    async def describe_image(self, message, user_id=None):
        '''
        Describe image that was sent by user
        '''
        if self.vision == False:
            return None
        try:
            prompt_tokens, completion_tokens = 0, 0
            summary = None
            message_copy = message.copy()   
            # Check if there is images in message
            if 'content' in message_copy and type(message_copy.content) == list:
                # Describe image
                success = False
                for i in range(len(message_copy.content)):
                    if message_copy.content[i]['type'] == 'image_url':
                        image_url = message_copy.content[i]['image_url']
                        success = True
                        break
                if success == False:
                    return None, {"prompt": 0, "completion": 0}
                new_message = {
                    "role": 'user',
                    "content": [{
                            "type": "text",
                            "text": "Describe given image, answer with description only."
                        },
                        {
                            "type": "image_url",
                            "image_url": image_url
                        }
                    ]
                }

                response = await self.client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=420,
                        messages=[new_message],
                        user=str(user_id)
                )

                prompt_tokens = int(response.usage.prompt_tokens)
                completion_tokens = int(response.usage.completion_tokens)
                summary = response.choices[0].message.content

                logger.debug(f'Image was summarized by OpenAI API to: {summary}')
            return summary, {"prompt": prompt_tokens, "completion": completion_tokens}
        except Exception as e:
            logger.exception('Could not describe image')
            return None, {"prompt": 0, "completion": 0}

    async def delete_images(self, messages):
        '''
        Filter out images from chat history, replace them with text
        '''
        try:
            # Check if there is images in messages
            for i in range(len(messages)):
                # Leave only text in message
                text, trimmed = await leave_only_text(messages[i], logger=logger)
                if trimmed == False:
                    # no images in message
                    continue
                text = text.content
                
                if self.image_description:
                    image_description, token_usage = await self.describe_image(messages[i])
                    tokens_prompt = int(token_usage['prompt'])
                    tokens_completion = int(token_usage['completion'])
                    text += f'\n<There was an image here, but it was deleted. Image description: `{image_description}`>'
                else:
                    tokens_prompt, tokens_completion = 0, 0
                    text += '\n<There was an image here, but it was deleted from the dialog history.>'

                new_message = Message()
                new_message.content = text
                new_message.role = messages[i].role
                new_message.tokens = {
                    'prompt': messages[i].tokens['prompt'] + tokens_prompt,
                    'completion': messages[i].tokens['completion'] + tokens_completion
                }
                messages[i] = new_message
                logger.debug(f'Image was deleted from chat history')

            return messages
        except Exception as e:
            logger.exception('Could not filter images')
            return None


######## YandexGPT Engine ########

class YandexEngine:
    def __init__(self, text=False) -> None:
        '''
        Initialize Yandex API for text generation
        '''
        self.name = 'YandexGPT'
        import requests 
        import json
        self.requests = requests
        self.json = json
        self.text_init() 

        self.headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Api-Key {self.chat_vars['SecretKey']}",
                'x-folder-id': self.chat_vars['CatalogID'],
            }
        if self.chat_vars['RequestLogging'] == False:
            self.headers['x-data-logging-enabled'] = 'false'

        # Get the encoding for the model
        self.model_encoding = None
        self.fallback_enc_base = 'cl100k_base'
        logger.info(f"Loading encoding for `{self.fallback_enc_base}` for estimating token usage")
        self.model_encoding = tiktoken.get_encoding(self.fallback_enc_base)
        
        logger.info('Yandex Engine was initialized')

    def text_init(self):
        '''
        Initialize Yandex API for text generation
        '''
        self.config = configparser.SafeConfigParser({
            "Endpoint": "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            "ChatModel": "yandexgpt-lite/latest",
            "SummarisationModel": "summarization/latest",
            "ChatModelCompletionPrice": 0,
            "ChatModelPromptPrice": 0,
            "PartialResults": False,
            "Temperature": 0.7,
            "MaxTokens": 1500,
            "SystemMessage": "You are a helpful chatbot assistant named Sir Chatalot.",
            "SummarizeTooLong": False,
            "ChatDeletion": False,
            "ImageSize": 512,            
            "MaxFileLength": 10000,
            "MinLengthTokens": 100,
            "EndUserID": False,
            "RequestLogging": False,
            "FunctionCalling": False,
            })
        self.config.read('./data/.config', encoding='utf-8')
        self.chat_vars = {} 
        self.chat_vars['SecretKey'] = self.config.get("YandexGPT", "SecretKey")   
        self.chat_vars['CatalogID'] = self.config.get("YandexGPT", "CatalogID")
        self.chat_vars['Endpoint'] = self.config.get("YandexGPT", "Endpoint")
        self.chat_vars['Model'] = self.config.get("YandexGPT", "ChatModel")
        self.chat_vars['SummarisationModel'] = self.config.get("YandexGPT", "SummarisationModel")
        self.chat_vars['Temperature'] = self.config.getfloat("YandexGPT", "Temperature")
        self.chat_vars['MaxTokens'] = self.config.getint("YandexGPT", "MaxTokens")
        self.chat_vars['SystemMessage'] = self.config.get("YandexGPT", "SystemMessage")
        self.chat_vars['MaxSessionLength'] = self.config.getint("YandexGPT", "MaxSessionLength") if self.config.has_option("YandexGPT", "MaxSessionLength") else None
        self.chat_vars['MaxSummaryTokens'] = self.config.getint("YandexGPT", "MaxSummaryTokens") if self.config.has_option("YandexGPT", "MaxSummaryTokens") else (self.chat_vars['MaxTokens'] // 2)
        self.chat_vars['RequestLogging'] = self.config.getboolean("YandexGPT", "RequestLogging")
        self.chat_vars['EndUserID'] = self.config.getboolean("YandexGPT", "EndUserID")
        self.chat_deletion = self.config.getboolean("YandexGPT", "ChatDeletion") 
        self.log_chats = self.config.getboolean("Logging", "LogChats") if self.config.has_option("Logging", "LogChats") else False
        
        if self.chat_vars['Model'].startswith('gpt://') or self.chat_vars['Model'].startswith('ds://'):
            # if model is already in correct format (gpt://<folder_ID>/yandexgpt/latest)
            pass
        else:
            # if model is not in correct format, add gpt://<folder_ID>/ to the beginning
            self.chat_vars['Model'] = f"gpt://{self.chat_vars['CatalogID']}/{self.chat_vars['Model']}"

        self.model = self.chat_vars['Model']
        self.system_message = self.chat_vars['SystemMessage']
        self.max_tokens = self.chat_vars['MaxTokens']
        self.model_completion_price = float(self.config.get("YandexGPT", "ChatModelCompletionPrice")) 
        self.model_prompt_price = float(self.config.get("YandexGPT", "ChatModelPromptPrice")) 
        self.summarize_too_long = self.config.getboolean("YandexGPT", "SummarizeTooLong") 
        self.max_chat_length = self.chat_vars['MaxSessionLength']        
        self.max_file_length = int(self.config.get("YandexGPT", "MaxFileLength"))
        self.min_length_tokens = int(self.config.get("YandexGPT", "MinLengthTokens")) 
        self.end_user_id = self.chat_vars['EndUserID']

        self.vision = False # Not supported yet
        self.function_calling = False # Not supported yet
        if self.vision:
            self.image_size = int(self.config.get("YandexGPT", "ImageSize")) 
            self.delete_image_after_chat = self.config.getboolean("YandexGPT", "DeleteImageAfterAnswer") if self.config.has_option("YandexGPT", "DeleteImageAfterAnswer") else False
            self.image_description = self.config.getboolean("YandexGPT", "ImageDescriptionOnDelete") if self.config.has_option("YandexGPT", "ImageDescriptionOnDelete") else False
        if self.max_chat_length is not None:
            print('Max chat length:', self.max_chat_length)
            print('-- Max chat length is states a length of chat session. It can be changed in the self.config file.\n')
        if self.chat_deletion:
            print('Chat deletion is enabled')
            print('-- Chat deletion is used to force delete old chat sessions. Without it long sessions should be summaried. It can be changed in the self.config file.\n')
        if self.vision:
            print('Vision is enabled')
            print('-- Vision is used to describe images and delete them from chat history. It can be changed in the self.config file.')
            print('-- Learn more: https://docs.anthropic.com/claude/docs/vision\n')

    async def chat(self, id=0, messages=None, attempt=0):
        '''
        Chat with Yandex GPT
        Input id of user and message
        Input:
          * id - id of user
          * messages = [
                {"role": "system", "content": "You are a helpful assistant named Sir Chat-a-lot."},
                {"role": "user", "content": "Hello, how are you?"},
                {"role": "assistant", "content": "I am fine, how are you?"},
                ...]
          * attempt - attempt to send message
        Output:
            * response - response from Yandex GPT (just text of last reply)
            * messages - messages from Yandex GPT (all messages - list of dictionaries with last message at the end)
            * tokens - number of tokens used in response (dict - {"prompt": int, "completion": int})
            If not successful returns None
        If messages tokens are more than 80% of max_tokens, it will be trimmed. 20% of tokens are left for response.
        '''
        if messages is None:
            return None, None, None
        prompt_tokens, completion_tokens = 0, 0
        # get response from Claude
        try:
            messages_tokens = await self.count_tokens(messages)
            if messages_tokens is None:
                messages_tokens = 0

            requested_tokens = min(self.max_tokens, self.max_tokens - messages_tokens)
            requested_tokens = max(requested_tokens, 50)
            new_messages = await self.revise_messages(messages)
            
            # POST request to Yandex API
            payload = {
                "modelUri": self.chat_vars['Model'],
                "completionOptions": {
                    "stream": False,
                    "temperature": self.chat_vars['Temperature'],
                    "maxTokens": requested_tokens,
                },
                "messages": new_messages
            }
            response = self.requests.post(self.chat_vars['Endpoint'], json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.debug(f'Yandex GPT response: {response.text}')
                response = self.json.loads(response.text)
                prompt_tokens = int(response['result']['usage']['inputTextTokens'])
                completion_tokens = int(response['result']['usage']['completionTokens'])
                response = str(response['result']['alternatives'][0]['message']['text'])
            elif response.status_code == 500:
                logger.error(f'Yandex GPT InternalServerError: {response.text} (code: {response.status_code})')
                return 'Yandex API service is having troubles. Please try again later.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
            elif response.status_code == 400:
                logger.error(f'Yandex GPT BadRequestError: {response.text} (code: {response.status_code})')
                return 'Yandex API service received a bad request. Please try again later or try to /delete session.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
            elif response.status_code == 401:
                logger.error(f'Yandex GPT UnauthorizedError: {response.text} (code: {response.status_code})')
                return 'Yandex API service is not authorized. Please contact the administrator.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
            elif response.status_code == 429:
                logger.error(f'Yandex GPT RateLimitError: {response.text} (code: {response.status_code})')
                return 'Service is getting rate limited. Please try again later.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
            # TODO: Chat is too long - check 
            elif response.status_code == 413:
                logger.error(f'Yandex GPT PayloadTooLarge: {response.text} (code: {response.status_code})')
                if self.chat_deletion or attempt > 0:
                    logger.debug(f'Chat session for user {id} was deleted due to an error')
                    messages = messages[0]
                    return 'We had to reset your chat session due to an error. Please try again.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}  
                else:
                    return 'Something went wrong. You can try to /delete session and start a new one.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
            else:
                logger.error(f'Yandex GPT Error: {response.text} (code: {response.status_code})')
                return "Something went wrong with Yandex GPT. Please try again later.", messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        except self.requests.exceptions.ConnectionError as e:
            logger.error(f'Connection error to Yandex API: {e}')
            return 'Yandex API service is not available. Please try again later.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        except Exception as e:
            logger.error(f'Something went wrong with attempt to get response from Yandex GPT: {e}')
            return None, messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # add response to chat history
        messages.append({"role": "assistant", "content": str(response)})
        # save chat history to file
        if self.max_chat_length is not None:
            if self.chat_deletion:
                l = len([i for i in messages if i['role'] == 'user'])
                if self.max_chat_length - l <= 3:
                    response += '\n*System*: You are close to the session limit. Messages left: ' + str(self.max_chat_length - l) + '.'
        if attempt == 1:
            # if chat is too long, return response and advice to delete session
            response += '\nIt seems like you reached length limit of chat session. You can continue, but I advice you to /delete session.'
        return response, messages, {"prompt": prompt_tokens, "completion": completion_tokens}
    
    async def revise_messages(self, messages):
        '''
        Format messages for Yandex API
        From: [{"role": "string", "content": "string"}, ...]
        To: [{"role": "string", "text": "string"}, ...]
        Also delete message with role "system"
        '''
        try:
            revised_messages = []
            for message in messages:
                revised_messages.append({"role": message['role'], "text": message['content']})
            return revised_messages
        except Exception as e:
            logger.exception('Could not revise messages for Yandex API')
            raise Exception('Could not revise messages for YandexGPT API')

    async def summary(self, text, size=420):
        '''
        Make summary of text
        Input text and size of summary (in tokens)
        '''
        try:
            # Get a summary prompt
            # Get the response from the API
            requested_tokens = min(size, self.max_tokens)
            # POST request to Yandex API
            payload = {
                "modelUri": f"gpt://{self.chat_vars['CatalogID']}/{self.chat_vars['SummarisationModel']}",
                "completionOptions": {
                    "stream": False,
                    "temperature": self.chat_vars['Temperature'],
                    "maxTokens": requested_tokens,
                },
                "messages": [
                    {"role": "user", "text": str(text)}
                ]
            }
            
            response = self.requests.post(self.chat_vars['Endpoint'], json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.debug(f'Yandex GPT response: {response.text}')
                response = self.json.loads(response.text)
                prompt_tokens = int(response['result']['usage']['inputTextTokens'])
                completion_tokens = int(response['result']['usage']['completionTokens'])
                response = str(response['result']['alternatives'][0]['message']['text'])
            else:
                logger.error(f'Yandex GPT Error: {response.text} (code: {response.status_code})')
                return None, {"prompt": 0, "completion": 0}
            # Return the response
            return response, {"prompt": prompt_tokens, "completion": completion_tokens}
        except Exception as e:
            logger.exception('Could not summarize text')
            return None, {"prompt": 0, "completion": 0}
    
    async def chat_summary(self, messages, short=False):
        '''
        Summarize chat history
        Input messages and short flag (states that summary should be in one sentence)
        '''
        try:
            if messages is None or len(messages) == 0:
                return None
            text = ''
            # Concatenate all messages into a single string
            for i in range(1, len(messages)):
                text += messages[i]['role'] + ': ' + str(messages[i]['content']) + '\n'
            if short:
                # Generate short summary
                summary = await self.summary(text, size=30)
            else:
                # Generate long summary
                summary = await self.summary(text)
            return summary
        except Exception as e:
            logger.exception('Could not summarize chat history')
            return None
    
    async def count_tokens(self, messages):
        '''
        Count tokens in messages via tiktoken
        '''
        try:
            # If messages empty
            if messages is None:
                logger.debug('Messages are empty')
                return None
            if len(messages) == 0:
                return 0
            # Count the number of tokens
            tokens = 0
            for message in messages:
                # Check if there is images in message and leave only text
                if self.vision:
                    message, trimmed = await leave_only_text(message, logger=logger)
                text = f"{message['role']}: {message['content']}"
                tokens += len(self.model_encoding.encode(text))
            logger.debug(f'Messages were counted for tokens: {tokens}')
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
        

######## Anthropic Engine ########
    
class AnthropicEngine:
    def __init__(self):
        '''
        Initialize Anthropic API for text generation
        '''
        self.name = 'Anthropic'
        from anthropic import AsyncAnthropic
        import anthropic 
        self.anthropic = anthropic
        self.config = configparser.SafeConfigParser({
            "ChatModel": "claude-3-haiku-20240307",
            "ChatModelCompletionPrice": 0,
            "ChatModelPromptPrice": 0,
            "Temperature": 0.7,
            "MaxTokens": 3997,
            "EndUserID": False,
            "ChatDeletion": False,
            "SystemMessage": "You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages.",
            "MaxFileLength": 10000,
            "MinLengthTokens": 100,
            "Vision": False,
            "ImageSize": 512,
            "SummarizeTooLong": False,
            "FunctionCalling": False,
            })
        self.config.read('./data/.config', encoding='utf-8')   
        # check if alternative API base is used
        self.base_url = None
        if self.config.has_option("Anthropic", "APIBase"):
            if str(self.config.get("Anthropic", "APIBase")).lower() not in ['default', '', 'none', 'false']:
                self.base_url = self.config.get("Anthropic", "APIBase")
            else:
                self.base_url = None
        # Set up the API 
        # TODO: working with other parameters
        proxy = self.config.get("Anthropic", "Proxy") if self.config.has_option("Anthropic", "Proxy") else None
        # proxy = {"http://": proxy, "https://": proxy} if proxy else None
        self.client = AsyncAnthropic(
            api_key=self.config.get("Anthropic", "SecretKey"),
            base_url=self.base_url,
            proxies=proxy,
        )
        self.function_calling = False
        self.text_init()      
        if self.function_calling:
            self.function_calling_tools = None

        self.model_encoding = None
        self.fallback_enc_base = 'cl100k_base'
        logger.info(f"Loading encoding for `{self.fallback_enc_base}` for estimating token usage")
        self.model_encoding = tiktoken.get_encoding(self.fallback_enc_base)

        logger.info('Anthropic Engine was initialized')

    def text_init(self):
        '''
        Initialize text generation
        '''
        self.model = self.config.get("Anthropic", "ChatModel")
        self.temperature = float(self.config.get("Anthropic", "Temperature"))
        self.max_tokens = int(self.config.get("Anthropic", "MaxTokens"))
        self.end_user_id = self.config.getboolean("Anthropic", "EndUserID") 
        self.system_message = self.config.get("Anthropic", "SystemMessage")
        self.file_summary_tokens = int(self.config.get("Anthropic", "MaxSummaryTokens")) if self.config.has_option("Anthropic", "MaxSummaryTokens") else (self.max_tokens // 2)
        self.max_file_length = int(self.config.get("Anthropic", "MaxFileLength"))
        self.min_length_tokens = int(self.config.get("Anthropic", "MinLengthTokens")) 
        self.max_chat_length = int(self.config.get("Anthropic", "MaxSessionLength")) if self.config.has_option("Anthropic", "MaxSessionLength") else None
        self.chat_deletion = self.config.getboolean("Anthropic", "ChatDeletion")
        self.log_chats = self.config.getboolean("Logging", "LogChats") if self.config.has_option("Logging", "LogChats") else False
        self.summarize_too_long = self.config.getboolean("Anthropic", "SummarizeTooLong") 
        self.model_completion_price = float(self.config.get("Anthropic", "ChatModelCompletionPrice")) 
        self.model_prompt_price = float(self.config.get("Anthropic", "ChatModelPromptPrice")) 

        self.vision = self.config.getboolean("Anthropic", "Vision")
        self.function_calling = self.config.getboolean("Anthropic", "FunctionCalling") 
        if self.vision:
            self.image_size = int(self.config.get("Anthropic", "ImageSize")) 
            self.delete_image_after_chat = self.config.getboolean("Anthropic", "DeleteImageAfterAnswer") if self.config.has_option("Anthropic", "DeleteImageAfterAnswer") else False
            self.image_description = self.config.getboolean("Anthropic", "ImageDescriptionOnDelete") if self.config.has_option("Anthropic", "ImageDescriptionOnDelete") else False

        if self.max_chat_length is not None:
            print('Max chat length:', self.max_chat_length)
            print('-- Max chat length is states a length of chat session. It can be changed in the self.config file.\n')
        if self.chat_deletion:
            print('Chat deletion is enabled')
            print('-- Chat deletion is used to force delete old chat sessions. Without it long sessions should be summaried. It can be changed in the self.config file.\n')
        if self.vision:
            print('Vision is enabled')
            print('-- Vision is used to describe images and delete them from chat history. It can be changed in the self.config file.')
            print('-- Learn more: https://docs.anthropic.com/claude/docs/vision\n')
        if self.function_calling:
            print('Function calling (tool use) is enabled')
            print('-- Function calling is used to call functions from chat. It can be changed in the self.config file.')
            print('-- Learn more: https://docs.anthropic.com/claude/docs/tool-use\n')

    async def revise_messages(self, messages):
        '''
        Revise messages from OpenAI API format to Anthropic format
        Input:
            * messages - list of dictionaries with messages
        Output:
            * system_prompt - system message
            * new_messages - list of dictionaries with revised messages
        '''
        try:
            new_messages = [{"role": "user", "content": []}]
            system_prompt = ""
            if messages is None:
                return system_prompt, None
            logger.debug(f'Messages to revise for Anthropic: {len(messages)}')
            # roles must alternate between "user" and "assistant"
            # itterate over messages
            i = 0
            last_role = 'user'
            for i in range(len(messages)):
                message = messages[i]
                if message['role'] == 'system':
                    system_prompt += f"{message['content']}\n"
                    continue
                
                # first message must use the "user" role and text should not be empty
                if i == 0 and message['role'] != 'user':
                    new_messages[-1]['content'].extend([{"type": "text", "text": "<start>"}])
                
                current_role = 'assistant' if message['role'] == 'assistant' else 'user'
                current_content = message['content']

                # check if there is images in message
                if self.vision and type(current_content) == list:
                    tmp = []
                    for i in range(len(current_content)):
                        if 'type' in current_content[i]:
                            if current_content[i]['type'] == 'image_url':
                                tmp.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": current_content[i]['image_url']['url'].split(';base64,')[0].split(':')[1],
                                        "data": current_content[i]['image_url']['url'].split(';base64,')[1]
                                    }
                                })
                            else:
                                tmp.append(current_content[i])
                        else:
                            tmp.append(current_content[i])
                    current_content = tmp

                if type(current_content) == str:
                    current_content = [{"type": "text", "text": current_content}]

                if last_role == current_role:
                    # extend the last message
                    new_messages[-1]['content'].extend(current_content)
                else:
                    new_messages.append({"role": current_role, "content": current_content})

                last_role = current_role
            return system_prompt, new_messages
        except Exception as e:
            logger.error(f'Could not revise messages for Anthropic: {e}')
            return "", None
        
    async def detect_function_called(self, response):
        '''
        Detect function called in response
        Input:
            * response - response from Anthropic API
        Output:
            * response - revised response if function was called, otherwise the same response
        '''
        response_message = None
        function_name = None
        function_args = None
        text = None
        tool_id = None
        try:
            logger.debug(f'Detecting function called in response: "{response}"')
            if response is None:
                return response
            if not self.function_calling:
                return response
            if self.function_calling_tools is None:
                return response
            if len(self.function_calling_tools) == 0:
                return response
            
            text = None
            if response.stop_reason == 'tool_use':
                logger.debug(f'Function was called in response')
                for content in response.content:
                    if type(content) == self.anthropic.types.TextBlock:
                        text = content.text
                    if type(content) == self.anthropic.types.ToolUseBlock:
                        function_name = content.name
                        function_args = content.input
                        tool_id = content.id
                tokens = {
                    "prompt": response.usage.input_tokens,
                    "completion": response.usage.output_tokens
                }
                return ('function', function_name, function_args, tokens, text, tool_id)
            return response
        except Exception as e:
            logger.error(f'Could not detect function called: {e}. Response: {response_message}')
            return response

    async def chat(self, id=0, messages=None, attempt=0):
        '''
        Chat with Claude
        Input id of user and message
        Input:
          * id - id of user
          * messages = [
                {"role": "system", "content": "You are a helpful assistant named Sir Chat-a-lot."},
                {"role": "user", "content": "Hello, how are you?"},
                {"role": "assistant", "content": "I am fine, how are you?"},
                ...]
          * attempt - attempt to send message
        Output:
            * response - response from Claude (just text of last reply)
            * messages - messages from Claude (all messages - list of dictionaries with last message at the end)
            * tokens - number of tokens used in response (dict - {"prompt": int, "completion": int})
            If not successful returns None
        If messages tokens are more than 80% of max_tokens, it will be trimmed. 20% of tokens are left for response.
        '''
        if messages is None:
            return None, None, None
        prompt_tokens, completion_tokens = 0, 0
        # get response from Claude
        try:
            messages_tokens = await self.count_tokens(messages)
            if messages_tokens is None:
                messages_tokens = 0

            # user_id = hashlib.sha1(str(id).encode("utf-8")).hexdigest() if self.end_user_id else None
            requested_tokens = min(self.max_tokens, self.max_tokens - messages_tokens)
            requested_tokens = max(requested_tokens, 50)
            system_prompt, new_messages = await self.revise_messages(messages)
            if self.function_calling:
                response = await self.client.messages.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=requested_tokens,
                        system=system_prompt,
                        messages=new_messages,
                        tools=self.function_calling_tools,
                )
                response = await self.detect_function_called(response)
                if response is not None:
                    if type(response) == tuple:
                        if response[0] == 'function':
                            logger.info(f'Function {response[1]} was called by user {id}')
                            return response, messages, response[3]
            else:
                response = await self.client.messages.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=requested_tokens,
                        system=system_prompt,
                        messages=new_messages
                )
            prompt_tokens = int(response.usage.input_tokens)
            completion_tokens = int(response.usage.output_tokens)
            # Delete images from chat history
            if self.vision and self.delete_image_after_chat:
                messages, token_usage = await self.delete_images(messages)
                prompt_tokens += int(token_usage['prompt'])
                completion_tokens += int(token_usage['completion'])

        # if connection problems
        except self.anthropic.APIConnectionError as e:
            logger.error(f'Anthropic APIConnectionError: {e}')
            return 'Anthropic service is not available. Please try again later.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # if ratelimit is reached
        except self.anthropic.RateLimitError as e:
            logger.error(f'Anthropic RateLimitError: {e}')
            return 'Service is getting rate limited. Please try again later.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # if chat is too long
        except self.anthropic.BadRequestError as e:
            if 'does not exist' in str(e):
                logger.error(f'Invalid model error for model {self.model}')
                return 'Something went wrong with an attempt to use the model. Please contact the administrator.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens} 
            logger.error(f'Invalid request error: {e}')
            if self.chat_deletion or attempt > 0:
                logger.debug(f'Chat session for user {id} was deleted due to an error')
                messages = messages[0]
                return 'We had to reset your chat session due to an error. Please try again.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}  
            else:
                return 'Something went wrong. You can try to /delete session and start a new one.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # if something else
        except Exception as e:
            logger.error(f'Could not get response from Claude: {e}')
            return None, messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # process response
        response = response.content[0].text
        # add response to chat history
        messages.append({"role": "assistant", "content": str(response)})
        # save chat history to file
        if self.max_chat_length is not None:
            if self.chat_deletion:
                l = len([i for i in messages if i['role'] == 'user'])
                if self.max_chat_length - l <= 3:
                    response += '\n*System*: You are close to the session limit. Messages left: ' + str(self.max_chat_length - l) + '.'
        if attempt == 1:
            # if chat is too long, return response and advice to delete session
            response += '\nIt seems like you reached length limit of chat session. You can continue, but I advice you to /delete session.'
        return response, messages, {"prompt": prompt_tokens, "completion": completion_tokens}

    async def summary(self, text, size=400):
        '''
        Make summary of text
        Input text and size of summary (in tokens)
        '''
        # Get a summary prompt
        system_prompt = f'You are very great at summarizing text to fit in {size//30} sentenses. Answer with summary only.'
        summary = []
        summary.append({"role": "user", "content": 'Make a summary:\n' + str(text)})
        # Get the response from the API
        requested_tokens = min(size, self.max_tokens)
        response = await self.client.messages.create(
                model=self.model,
                temperature=self.temperature, 
                max_tokens=requested_tokens,
                system=system_prompt,
                messages=summary
        )
        prompt_tokens = int(response.usage.input_tokens)
        completion_tokens = int(response.usage.output_tokens)
        response = response.content[0].text 
        # Return the response
        return response, {"prompt": prompt_tokens, "completion": completion_tokens}

    async def chat_summary(self, messages, short=False):
        '''
        Summarize chat history
        Input messages and short flag (states that summary should be in one sentence)
        '''
        try:
            if messages is None or len(messages) == 0:
                return None
            text = ''
            prompt_tokens, completion_tokens = 0, 0
            # Concatenate all messages into a single string
            for i in range(1, len(messages)):
                message = messages[i]
                image_description, token_usage = await self.describe_image(message)
                if image_description is None:
                    text += message['role'] + ': ' + str(message['content']) + '\n'
                else:
                    text += message['role'] + ': ' + '<There was an image here, description: ' + image_description + '\n'
                prompt_tokens += int(token_usage['prompt'])
                completion_tokens += int(token_usage['completion'])
            if short:
                # Generate short summary
                summary, token_usage = await self.summary(text, size=30)
                prompt_tokens += int(token_usage['prompt'])
                completion_tokens += int(token_usage['completion'])
            else:
                # Generate long summary
                summary, token_usage = await self.summary(text)
                prompt_tokens += int(token_usage['prompt'])
                completion_tokens += int(token_usage['completion'])
            return summary, {"prompt": prompt_tokens, "completion": completion_tokens}
        except Exception as e:
            logger.exception('Could not summarize chat history')
            return None, {"prompt": 0, "completion": 0}

    async def count_tokens(self, messages):
        '''
        Count tokens in messages via tiktoken
        '''
        try:
            # If messages empty
            if messages is None:
                logger.debug('Messages are empty')
                return None
            if len(messages) == 0:
                return 0
            # Count the number of tokens
            tokens = 0
            for message in messages:
                # Check if there is images in message and leave only text
                if self.vision:
                    message, trimmed = await leave_only_text(message, logger=logger)
                text = f"{message['role']}: {message['content']}"
                tokens += len(self.model_encoding.encode(text))
            logger.debug(f'Messages were counted for tokens: {tokens}')
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
        
    async def describe_image(self, message, user_id=None):
        '''
        Describe image that was sent by user
        '''
        if self.vision == False:
            # no need to describe
            return None
        try:
            prompt_tokens, completion_tokens = 0, 0
            summary = None
            message_copy = message.copy()   
            # Check if there is images in message
            if 'content' in message_copy and type(message_copy['content']) == list:
                # Describe image
                success = False
                for i in range(len(message_copy['content'])):
                    if message_copy['content'][i]['type'] == 'image_url':
                        image_url = message_copy['content'][i]['image_url']
                        success = True
                        break
                if success == False:
                    return None, {"prompt": 0, "completion": 0}
                new_message = {
                    "role": 'user',
                    "content": [{
                            "type": "text",
                            "text": "Describe given image, answer with description only."
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_url,
                            },
                        }
                    ]
                }

                response = await self.client.messages.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=400,
                        messages=[new_message],
                        # user=str(user_id)
                )
                prompt_tokens = int(response.usage.input_tokens)
                completion_tokens = int(response.usage.output_tokens)
                summary = response.content[0].text 
                # log to logger file fact of message being received
                logger.debug(f'Image was summarized by Anthropic API to: {summary}')
            return summary, {"prompt": prompt_tokens, "completion": completion_tokens}
        except Exception as e:
            logger.error(f'Could not describe image with Anthropic API: {e}')
            return None, {"prompt": 0, "completion": 0}

    async def delete_images(self, messages):
        '''
        Filter out images from chat history, replace them with text
        '''
        if self.vision == False:
            # no need to filter
            return None
        try:
            tokens_prompt, tokens_completion = 0, 0
            # Check if there is images in messages
            for i in range(len(messages)):
                # Leave only text in message
                text, trimmed = await leave_only_text(messages[i], logger=logger)
                if trimmed == False:
                    # no images in message
                    continue
                text = text['content'] 
                if self.image_description:
                    image_description, token_usage = await self.describe_image(messages[i])
                    tokens_prompt += int(token_usage['prompt'])
                    tokens_completion += int(token_usage['completion'])
                    text += f'\n<There was an image here, but it was deleted. Image description: {image_description} Resend the image if you needed.>'
                else:
                    text += '\n<There was an image here, but it was deleted from the dialog history to keep low usage of API. Resend the image if you needed.>'
                messages[i] = {"role": messages[i]['role'], "content": text}
                logger.debug(f'Image was deleted from chat history')
            return messages, {"prompt": tokens_prompt, "completion": tokens_completion}
        except Exception as e:
            logger.exception('Could not filter images')
            return None, {"prompt": 0, "completion": 0}
        
def get_text_engine(engine_name="openai"):
    '''
    Get text engine by name
    Possible engines:
    * openai
    * yandex (yandexgpt)
    * anthropic (claude)
    Default engine is OpenAI
    '''
    if engine_name.lower() in ["openai"]:
        return OpenAIEngine()
    elif engine_name.lower() in ["yandex", "yandexgpt"]:
        return YandexEngine()
    elif engine_name.lower() in ["anthropic", "claude"]:
        return AnthropicEngine()
    else:
        raise ValueError(f"Unsupported text engine: {engine_name}")


####### TEST #######
if __name__ == '__main__':
    # engine = OpenAIEngine(text=True)
    engine = YandexEngine(text=True)
    # engine = AnthropicEngine(text=True)

    messages = [
        {"role": "system", "content": "Your name is Sir Chatalot, you are assisting the user with a task."},
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I am fine, how are you?"},
        {"role": "user", "content": "I am fine too. Please tell me what is the weather like today?"},
    ]
    print('\n***        Test        ***')
    response, messages, tokens = asyncio.run(engine.chat(messages=messages, id=0))
    print('============================')
    print(response)
    print('------------------')
    for message in messages:
        print(message['role'], ':', message['content'])
    print('----------------------------')
    print(tokens)
    print('============================')
