# Description: Chats processing class

import configparser
config = configparser.ConfigParser()
config.read('./data/.config')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

# logging
import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-Engines")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/sirchatalot.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import os
import hashlib
import tiktoken
import asyncio
import json
import time

######## OpenAI Engine ########

class OpenAIEngine:
    def __init__(self, text=False, speech=False):
        '''
        Initialize OpenAI API 
        Available: text generation, speech2text
        '''
        from openai import AsyncOpenAI
        import openai 
        self.openai = openai
        import configparser
        self.config = configparser.SafeConfigParser({
            "ChatModel": "gpt-3.5-turbo",
            "ChatModelCompletionPrice": 0,
            "ChatModelPromptPrice": 0,
            "WhisperModel": "whisper-1",
            "WhisperModelPrice": 0,
            "Temperature": 0.7,
            "MaxTokens": 3997,
            "AudioFormat": "wav",
            "EndUserID": False,
            "Moderation": False,
            "ChatDeletion": False,
            "SystemMessage": "You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages.",
            "MaxFileLength": 10000,
            "MinLengthTokens": 100,
            "Vision": False,
            "ImageSize": 512,
            "ImageGeneration": False,
            "ImageGenModel": "dall-e-3",
            "ImageGenerationSize": "1024x1024",
            "ImageGenerationStyle": "vivid",
            "ImageGenerationQuality": "standard",
            "ImageGenerationPrice": 0,
            "ImageRateLimitCount": 0,
            "ImageRateLimitTime": 0,
            "FunctionCalling": False,
            "SummarizeTooLong": False,
            })
        self.config.read('./data/.config')   
        # check if alternative API base is used
        self.base_url = None
        if self.config.has_option("OpenAI", "APIBase"):
            if str(self.config.get("OpenAI", "APIBase")).lower() not in ['default', '', 'none', 'false']:
                self.base_url = self.config.get("OpenAI", "APIBase")
            else:
                self.base_url = None
        # Set up the API 
        # TODO: working with other parameters
        self.client = AsyncOpenAI(
            api_key=self.config.get("OpenAI", "SecretKey"),
            base_url=self.base_url,
        )
        self.text_initiation, self.speech_initiation = text, speech
        self.text_init() if self.text_initiation else None
        self.speech_init() if self.speech_initiation else None

        logger.info('OpenAI Engine was initialized')

    def text_init(self):
        '''
        Initialize text generation
        '''
        self.model = self.config.get("OpenAI", "ChatModel")
        self.model_completion_price = float(self.config.get("OpenAI", "ChatModelCompletionPrice")) 
        self.model_prompt_price = float(self.config.get("OpenAI", "ChatModelPromptPrice")) 
        self.temperature = float(self.config.get("OpenAI", "Temperature"))
        self.max_tokens = int(self.config.get("OpenAI", "MaxTokens"))
        self.end_user_id = self.config.getboolean("OpenAI", "EndUserID") 
        self.system_message = self.config.get("OpenAI", "SystemMessage")
        self.file_summary_tokens = int(self.config.get("OpenAI", "MaxSummaryTokens")) if self.config.has_option("OpenAI", "MaxSummaryTokens") else (self.max_tokens // 2)
        self.max_file_length = int(self.config.get("OpenAI", "MaxFileLength"))
        self.min_length_tokens = int(self.config.get("OpenAI", "MinLengthTokens")) 
        self.moderation = self.config.getboolean("OpenAI", "Moderation")
        self.max_chat_length = int(self.config.get("OpenAI", "MaxSessionLength")) if self.config.has_option("OpenAI", "MaxSessionLength") else None
        self.chat_deletion = self.config.getboolean("OpenAI", "ChatDeletion")
        self.log_chats = self.config.getboolean("Logging", "LogChats") if self.config.has_option("Logging", "LogChats") else False
        self.summarize_too_long = self.config.getboolean("OpenAI", "SummarizeTooLong") 

        self.vision = self.config.getboolean("OpenAI", "Vision")
        self.image_size = int(self.config.get("OpenAI", "ImageSize")) 
        self.image_generation = self.config.getboolean("OpenAI", "ImageGeneration") 
        self.function_calling = self.config.getboolean("OpenAI", "FunctionCalling") 
        if self.image_generation:
            self.image_generation_size = self.config.get("OpenAI", "ImageGenerationSize")
            self.image_model = self.config.get("OpenAI", "ImageGenModel")
            self.image_generation_style = self.config.get("OpenAI", "ImageGenerationStyle") 
            self.image_generation_quality = self.config.get("OpenAI", "ImageGenerationQuality")
            self.image_generation_price = float(self.config.get("OpenAI", "ImageGenerationPrice"))
            self.image_rate_limit_count = int(self.config.get("OpenAI", "ImageRateLimitCount"))
            self.image_rate_limit_time = int(self.config.get("OpenAI", "ImageRateLimitTime"))
            self.image_rate_limit = {}
        if self.vision:
            self.delete_image_after_chat = self.config.getboolean("OpenAI", "DeleteImageAfterAnswer") if self.config.has_option("OpenAI", "DeleteImageAfterAnswer") else False
            self.image_description = self.config.getboolean("OpenAI", "ImageDescriptionOnDelete") if self.config.has_option("OpenAI", "ImageDescriptionOnDelete") else False
        if self.function_calling:
            self.function_calling_tools = None

        if self.max_chat_length is not None:
            print('Max chat length:', self.max_chat_length)
            print('-- Max chat length is states a length of chat session. It can be changed in the self.config file.\n')
        if self.chat_deletion:
            print('Chat deletion is enabled')
            print('-- Chat deletion is used to force delete old chat sessions. Without it long sessions should be summaried. It can be changed in the self.config file.\n')
        if self.moderation:
            print('Moderation is enabled')
            print('-- Moderation is used to check if content complies with OpenAI usage policies. It can be changed in the self.config file.')
            print('-- Learn more: https://platform.openai.com/docs/guides/moderation/overview\n')
        if self.vision:
            print('Vision is enabled')
            print('-- Vision is used to describe images and delete them from chat history. It can be changed in the self.config file.')
            print('-- Learn more: https://platform.openai.com/docs/guides/vision/overview\n')
        if self.image_generation:
            print('Image generation via DALL-E is enabled')
            print('-- Image generation is used to create images from text. It can be changed in the self.config file.')
            if self.image_rate_limit_count > 0 and self.image_rate_limit_time > 0:
                print(f'-- Image generation is rate limited (only {self.image_rate_limit_count} images per {self.image_rate_limit_time} seconds are allowed).')
            print('-- Learn more: https://platform.openai.com/docs/guides/images/usage\n')
        if self.function_calling:
            print('Function calling is enabled')
            print('-- Function calling is used to call functions from OpenAI API. It can be changed in the self.config file.')
            print('-- Learn more: https://platform.openai.com/docs/guides/function-calling\n')

    def speech_init(self):
        '''
        Initialize speech2text
        '''  
        self.s2t_model = self.config.get("OpenAI", "WhisperModel")
        self.s2t_model_price = float(self.config.get("OpenAI", "WhisperModelPrice")) 
        self.audio_format = '.' + self.config.get("OpenAI", "AudioFormat") 

    async def convert_ogg(self, audio_file):
        '''
        Convert ogg file to wav
        Input file with ogg
        '''
        try:
            converted_file = audio_file.replace('.ogg', self.audio_format)
            os.system('ffmpeg -i ' + audio_file + ' ' + converted_file)
            return converted_file
        except Exception as e:
            logger.exception(f'Could not convert ogg to {self.audio_format}')
            return None
        
    async def speech_to_text(self, audio_file):
        '''
        Convert speech to text using OpenAI API
        '''
        try:
            if self.speech_initiation == False:
                return None
            audio_file = await self.convert_ogg(audio_file)
            audio = open(audio_file, "rb")
            transcript = await self.client.audio.transcriptions.create(self.s2t_model, audio)
            audio.close()
            transcript = transcript['text']
            return transcript
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI RateLimitError: {e}')
            return 'Service is getting rate limited. Please try again later.'
        except Exception as e:
            logger.exception('Could not convert speech to text')
            return None
        
    async def generate_image(self, prompt, image_orientation=None, image_style=None):
        '''
        Generate image from text prompt
        Input:
            * prompt - text prompt
            * orientation - orientation of image (landscape, portrait, default is None - square)
            * style - style of image (natural or vivid, default is None - vivid)
        '''
        try:
            logger.debug(f'Generating image from prompt: {prompt}, orientation: {image_orientation}, style: {image_style}')
            if self.image_generation == False:
                return None, None
            if prompt is None:
                return None, None
            
            size="1024x1024"
            style="vivid"
            if image_orientation is not None:
                if image_orientation == 'landscape':
                    size = '1792x1024'
                if image_orientation == 'portrait':
                    size = '1024x1792'
            if image_style is not None:
                if image_style == 'natural':
                    style = 'natural'

            b64_image, revised_prompt = await self.imagine(prompt, id='function', size=size, style=style, n=1, quality="standard", revision=True)
            return (b64_image, revised_prompt)
        except Exception as e:
            logger.exception('Could not generate image')
            return None
        
    async def detect_function_called(self, response):
        '''
        TODO: Function calling is in highly experimental stage

        Detect if function was called in response
        Learn more: https://platform.openai.com/docs/guides/function-calling
        Input:
            * response - response from GPT
        Output:
            * response - response from GPT (None if function was not detected or there was an error)
        '''
        response_message = None
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
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            if not tool_calls:
                return response
            function_name = tool_calls[0].function.name
            function_args = json.loads(tool_calls[0].function.arguments)
            tokens = {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens
            }
            # return ('function', function_name, function_response, tokens)
            return ('function', function_name, function_args, tokens)
        except Exception as e:
            logger.error(f'Could not detect function called: {e}. Response: {response_message}')
            return response
        
    async def chat(self, id=0, messages=None, attempt=0):
        '''
        Chat with GPT
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
            * response - response from GPT (just text of last reply)
            * messages - messages from GPT (all messages - list of dictionaries with last message at the end)
            * tokens - number of tokens used in response (dict - {"prompt": int, "completion": int})
            If not successful returns None
        If messages tokens are more than 80% of max_tokens, it will be trimmed. 20% of tokens are left for response.
        '''
        if self.text_initiation == False:
            return None, None, None
        if messages is None:
            return None, None, None
        prompt_tokens, completion_tokens = 0, 0
        # send last message to moderation
        if self.moderation:
            if await self.moderation_pass(messages[-1], id) == False:
                return 'Your message was flagged as violating OpenAI\'s usage policy and was not sent. Please try again.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}    
        # get response from GPT
        try:
            messages_tokens = await self.count_tokens(messages)
            if messages_tokens is None:
                messages_tokens = 0

            user_id = hashlib.sha1(str(id).encode("utf-8")).hexdigest() if self.end_user_id else None
            requested_tokens = min(self.max_tokens, self.max_tokens - messages_tokens)
            requested_tokens = max(requested_tokens, 50)
            if self.function_calling:
                # TODO: working with function calling - now it is for testing only
                response = await self.client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=requested_tokens,
                        messages=messages,
                        user=str(user_id),
                        tools=self.function_calling_tools,
                        tool_choice="auto",
                )
                response = await self.detect_function_called(response)
                if response is not None:
                    if type(response) == tuple:
                        if response[0] == 'function':
                            logger.info(f'Function {response[1]} was called by user {id}')
                            return response, messages, response[3]
            else:
                response = await self.client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=requested_tokens,
                        messages=messages,
                        user=str(user_id)
                )

            prompt_tokens = int(response.usage.prompt_tokens)
            completion_tokens = int(response.usage.completion_tokens)

            # Delete images from chat history
            if self.vision and self.delete_image_after_chat:
                messages, token_usage = await self.delete_images(messages)
                prompt_tokens += int(token_usage['prompt'])
                completion_tokens += int(token_usage['completion'])

        # if ratelimit is reached
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI RateLimitError: {e}')
            return 'Service is limited. Please try again later.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # if chat is too long
        except self.openai.BadRequestError as e:
            # if 'openai.error.InvalidRequestError: The model: `gpt-4` does not exist'
            if 'does not exist' in str(e):
                logger.error(f'Invalid model error for model {self.model}')
                return 'Something went wrong with an attempt to use the model. Please contact the developer.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens} 
            logger.error(f'Invalid request error: {e}')
            if self.chat_deletion or attempt > 0:
                logger.debug(f'Chat session for user {id} was deleted due to an error')
                messages = messages[0]
                return 'We had to reset your chat session due to an error. Please try again.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}  
            else:
                return 'It seems that chat session is too long or something else happened. You can try to /delete session and start a new one.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # if something else
        except Exception as e:
            logger.exception('Could not get response from GPT')
            return None, messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # process response
        response = response.choices[0].message.content
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

    async def image_rate_limit_check(self, id):
        '''
        Check if image generation is not rate limited
        Return True if not rate limited, False if rate limited
        '''
        try:
            if self.image_rate_limit_count <= 0 or self.image_rate_limit_time <= 0:
                return True
            if id not in self.image_rate_limit:
                self.image_rate_limit[id] = []
            # add current time to the list
            current_time = time.time()
            self.image_rate_limit[id].append(current_time)
            # remove old times
            self.image_rate_limit[id] = [t for t in self.image_rate_limit[id] if current_time - t < self.image_rate_limit_time]
            # check if count is not exceeded
            if len(self.image_rate_limit[id]) > self.image_rate_limit_count:
                return False
            return True
        except Exception as e:
            logger.error(f'Could not check image rate limit due to an error: {e}')
            return True

    async def imagine(self, prompt, id=0, size="1024x1024", style="vivid", n=1, revision=False, quality="standard"):
        '''
        Create image from text prompt
        Input:
            * prompt - text prompt
            * id - id of user
            * size - size of image (1024x1024, 1792x1024, or 1024x1792 for dall-e-3)
            * style - style of image (natural or vivid)
            * n - number of images to generate (only 1 for dall-e-3)
            * revision - if True, returns revised prompt
            * quality - quality of image (standard or hd - only for dall-e-3)
            
        See https://platform.openai.com/docs/api-reference/images/create for more details

        You can use the following keywords in prompt:
            * --natural - for natural style
            * --vivid - for vivid style
            * --sd - for standard quality
            * --hd - for hd quality
            * --horizontal - for horizontal image
            * --vertical - for vertical image
        '''
        if self.image_generation == False:
            return None, None
        # check if image generation is not rate limited
        if self.image_generation:
            if await self.image_rate_limit_check(id) == False:
                return None, f'Image generation is rate limited (only {self.image_rate_limit_count} images per {round(self.image_rate_limit_time/60)} minutes are allowed). Please try again later.'
        try:
            prompt = prompt.replace('—', '--')
            # extract arguments from prompt (if any)
            if '--natural' in prompt:
                style = 'natural'
                prompt = prompt.replace('--natural', '')
            if '--vivid' in prompt:
                style = 'vivid'
                prompt = prompt.replace('--vivid', '')
            if '--sd' in prompt:
                quality = 'standard'
                prompt = prompt.replace('--sd', '')
            if '--hd' in prompt:
                quality = 'hd'
                prompt = prompt.replace('--hd', '')
            if '--horizontal' in prompt:
                if self.image_model == 'dall-e-3':
                    size = '1792x1024'
                prompt = prompt.replace('--horizontal', '')
            if '--vertical' in prompt:
                if self.image_model == 'dall-e-3':
                    size = '1024x1792'
                prompt = prompt.replace('--vertical', '')
            prompt = prompt.strip()
            if prompt == '':
                return None, 'No text prompt was given. Please try again.'
            revised_prompt, b64_image = None, None
            user_id = hashlib.sha1(str(id).encode("utf-8")).hexdigest() if self.end_user_id else None
            response = await self.client.images.generate(
                        model=self.image_model,
                        prompt=prompt,
                        size=size,
                        quality=quality,
                        n=n,
                        response_format="b64_json",
                        style=style,
                        user=str(user_id)
                    )
            if response.data[0].b64_json:
                b64_image = response.data[0].b64_json
            if revision:
                try:
                    revised_prompt = response.data[0].revised_prompt
                except Exception as e:
                    logger.warning(f'Could not get revised prompt: {e}')
                    revised_prompt = None
            return b64_image, revised_prompt
        except self.openai.BadRequestError as e:
            logger.error('OpenAI BadRequestError: ' + str(e))
            if 'content_policy_violation' in str(e):
                return None, 'Your request was rejected because it may violate content policy. Please review it and try again.'
            return None, 'Your request was rejected. Please review it and try again.'
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI RateLimitError: {e}')
            return None, 'Service is getting rate limited. Please try again later.'
        except Exception as e:
            logger.exception('Could not imagine image from text')
            return None, None

    async def summary(self, text, size=420):
        '''
        Make summary of text
        Input text and size of summary (in tokens)
        '''
        try:
            # Get a summary prompt
            summary = [{"role": "system", "content": f'You are very great at summarizing text. Answer to user message with summary only.'}]
            summary.append({"role": "user", "content": str(text)})
            # Get the response from the API
            requested_tokens = min(size, self.max_tokens)
            response = await self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature, 
                    max_tokens=requested_tokens,
                    messages=summary
            )
            prompt_tokens = int(response.usage.prompt_tokens)
            completion_tokens = int(response.usage.completion_tokens)

            # Return the response
            return response.choices[0].message.content, {"prompt": prompt_tokens, "completion": completion_tokens}
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
        
    async def moderation_pass(self, message, id=0):
        try:
            # check if message is not empty
            if message is None or len(message) == 0:
                return None
            # check if there is image in message and leave only text
            if self.vision:
                message, trimmed = await self.leave_only_text(message)
            response = await self.client.moderations.create(
                input=[message['content']],
                model='text-moderation-stable',
                )
            output = response.results[0]
            if output.flagged:
                categories = output.categories
                # get flagged categories
                flagged_categories = []
                for category in categories._asdict():
                    if categories._asdict()[category] == True:
                        flagged_categories.append(category)
                # log used id, flagged message and flagged categories to ./data/moderation.txt
                with open('./data/moderation.txt', 'a') as f:
                    f.write(str(id) + '\t' + str(flagged_categories) + '\t' + message + '\n')
                # log to logger file fact of user being flagged
                logger.info('Message from user ' + str(id) + ' was flagged (' + str(flagged_categories) + ')')
                return False
            return True
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI RateLimitError: {e}')
        except self.openai.InternalServerError as e:
            logger.error(f'OpenAI InternalServerError: {e}')
        except Exception as e:
            logger.exception('Could not moderate message')
            return None

    async def count_tokens(self, messages):
        '''
        Count tokens in messages via tiktoken
        '''
        try:
            # Get the encoding for the model
            encoding = tiktoken.encoding_for_model(self.model)
            # Count the number of tokens
            tokens = 0
            for message in messages:
                # Check if there is images in message and leave only text
                if self.vision:
                    message, trimmed = await self.leave_only_text(message)
                text = message['role'] + ': ' + message['content']
                tokens += len(encoding.encode(text))
            logger.debug(f'Messages were counted for tokens: {tokens}')
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
        
    async def leave_only_text(self, message):
        '''
        Leave only text in message with images
        '''
        if message is None:
            return None, False
        try:
            message_copy = message.copy()
            # Check if there is images in message
            trimmed = False
            if 'content' in message_copy and type(message_copy['content']) == list:
                # Leave only text in message
                for i in range(len(message_copy['content'])):
                    if message_copy['content'][i]['type'] == 'text':
                        message_copy['content'] = message_copy['content'][i]['text']
                        trimmed = True
                        break
            return message_copy, trimmed
        except Exception as e:
            logger.exception('Could not leave only text in message')
            return message, False
        
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
                    if message_copy['content'][i]['type'] == 'image':
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
                            "type": "image_url",
                            "image_url": image_url
                        }
                    ]
                }

                response = await self.client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=400,
                        messages=[new_message],
                        user=str(user_id)
                )

                prompt_tokens = int(response.usage.prompt_tokens)
                completion_tokens = int(response.usage.completion_tokens)
                summary = response.choices[0].message.content
                # log to logger file fact of message being received
                logger.debug(f'Image was summarized by OpenAI API to: {summary}')
            return summary, {"prompt": prompt_tokens, "completion": completion_tokens}
        except Exception as e:
            logger.exception('Could not describe image')
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
                text, trimmed = await self.leave_only_text(messages[i])
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


######## YandexGPT Engine ########

class YandexEngine:
    def __init__(self, text=False, speech=False) -> None:
        '''
        Initialize Yandex API for text generation
        Available: text generation
        '''
        import requests 
        import json
        self.requests = requests
        self.json = json
        self.text_initiation, self.speech_initiation = text, speech
        self.text_init() if self.text_initiation else None
        self.speech_init() if self.speech_initiation else None

    def text_init(self):
        '''
        Initialize Yandex API for text generation
        '''
        import configparser
        self.config = configparser.SafeConfigParser({
            "ChatEndpoint": "https://llm.api.cloud.yandex.net/llm/v1alpha/chat",
            "InstructEndpoint": "https://llm.api.cloud.yandex.net/llm/v1alpha/instruct",
            "ChatModel": "general",
            "PartialResults": False,
            "Temperature": 0.7,
            "MaxTokens": 1500,
            "instructionText": "You are a helpful chatbot assistant named Sir Chatalot.",
            "SummarizeTooLong": False,
            })
        self.config.read('./data/.config') 
        self.chat_vars = {} 
        self.chat_vars['KeyID'] = self.config.get("YandexGPT", "KeyID")  
        self.chat_vars['SecretKey'] = self.config.get("YandexGPT", "SecretKey")   
        self.chat_vars['CatalogID'] = self.config.get("YandexGPT", "CatalogID")
        self.chat_vars['Endpoint'] = self.config.get("YandexGPT", "ChatEndpoint")
        self.chat_vars['InstructEndpoint'] = self.config.get("YandexGPT", "InstructEndpoint")
        self.chat_vars['Model'] = self.config.get("YandexGPT", "ChatModel")
        self.model = self.chat_vars['Model']
        self.chat_vars['PartialResults'] = self.config.getboolean("YandexGPT", "PartialResults")
        self.chat_vars['Temperature'] = self.config.getfloat("YandexGPT", "Temperature")
        self.chat_vars['MaxTokens'] = self.config.getint("YandexGPT", "MaxTokens")
        self.chat_vars['instructionText'] = self.config.get("YandexGPT", "instructionText")
        self.chat_deletion = self.config.getboolean("YandexGPT", "ChatDeletion") if self.config.has_option("YandexGPT", "ChatDeletion") else True
        self.log_chats = self.config.getboolean("Logging", "LogChats") if self.config.has_option("Logging", "LogChats") else False
        self.system_message = self.chat_vars['instructionText']
        self.max_tokens = self.chat_vars['MaxTokens']
        self.model_prompt_price = 0
        self.model_completion_price = 0
        self.summarize_too_long = self.config.getboolean("YandexGPT", "SummarizeTooLong") 

        self.vision = False # Not supported yet
        self.image_generation = False # Not supported yet
        self.function_calling = False # Not supported yet

    def speech_init(self):
        '''
        Initialize Yandex API for speech synthesis
        '''
        # TODO: implement speech to text with Yandex API
        pass

    async def chat(self, messages, id=0, attempt=0):
        '''
        Chat with Yandex GPT
        Input id of user and message
        Input:
          * id - id of user
          * messages = [
                {"role": "user", "content": "Hello, how are you?"},
                {"role": "assistant", "content": "I am fine, how are you?"},
                ...]
          * attempt - attempt to send message
        Output:
            * response - response from GPT (just text of last reply)
            * messages - messages from GPT (all messages - list of dictionaries with last message at the end)
            * tokens - number of tokens used in response (dict - {"prompt": int, "completion": int})
            If not successful returns None
        '''
        try:
            completion_tokens = 0
            # count tokens in messages
            tokens = await self.count_tokens(messages)
            if tokens is not None:
                tokens = self.chat_vars['MaxTokens'] - tokens
                tokens = max(tokens, 30)
            else:
                tokens = self.chat_vars['MaxTokens'] // 2
            # make post request to Yandex API
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Api-Key {self.chat_vars['SecretKey']}",
                'x-folder-id': self.chat_vars['CatalogID']
            }
            payload = {
                "model": self.chat_vars['Model'],
                "generationOptions": {
                    "partialResults": self.chat_vars['PartialResults'],
                    "temperature": self.chat_vars['Temperature'],
                    "maxTokens": tokens
                },
                "messages": await self.format_messages(messages),
                "instructionText": self.chat_vars['instructionText']
            }
            logger.debug(f'Payload to Yandex API: {payload}')
            response = self.requests.post(self.chat_vars['Endpoint'], json=payload, headers=headers)
            logger.debug(f'Response from Yandex API. Code: {response.status_code}, text: {response.text}')
            # check if response is successful
            if response.status_code != 200:
                if response.status_code == 400 and attempt == 0:
                    if response.json()['error']['message'].startswith('Error in session'):
                        if self.chat_deletion:
                            logger.warning(f'Session is too long for user {id}, deleting and starting new session')
                            messages = [{"role": "system", "content": self.system_message}]
                            user_message = 'Sorry, apparently your session is too long so I have to delete it. Please start again.'
                            return user_message, messages, None
                        else:
                            logger.warning(f'Session is too long for user {id}, summarrizing and sending last message')
                            attempt += 1
                else:
                    logger.error(f'Could not send message to Yandex API, response status code: {response.status_code}, response: {response.json()}')
                    user_message = 'Sorry, something went wrong. Please try to /delete and /start again.'
                    return user_message, messages, None
            if attempt == 1:
                logger.warning(f'Session is too long for user {id}, summarrizing and sending last message')
                # summary messages
                style = messages[0]['content'] + '\n Your previous conversation summary: '
                style += await self.chat_summary(messages[:-1])
                response, messages, token_usage = await self.chat(id=id, messages=[{"role": "system", "content": style}, {"role": "user", "content": message}], attempt=attempt+1)
                completion_tokens += int(token_usage['completion']) if token_usage['completion'] else None
            # get response from Yandex API (example: {'result': {'message': {'role': 'Ассистент', 'text': 'The current temperature in your area right now (as of 10/23) would be approximately **75°F**.'}, 'num_tokens': '94'}})
            response = response.json()
            # lines = response.text.splitlines()
            # json_objects = [self.json.loads(line) for line in lines]
            # # Parse only the last line into JSON
            # response = json_objects[-1]

            response = response['result']
            completion_tokens += int(response['num_tokens']) if response['num_tokens'] else None
            response = str(response['message']['text']) if response['message']['text'] else None

            # log to logger file fact of message being received
            logger.debug('Message from user ' + str(id) + ' was received from Yandex API')
            messages.append({"role": "assistant", "content": response})
            return response, messages, {"prompt": 0, "completion": completion_tokens}
        except Exception as e:
            logger.exception('Could not send message to Yandex API')
            return None, messages, None

    async def format_messages(self, messages):
        '''
        Format messages for Yandex API
        From: [{"role": "string", "content": "string"}, ...]
        To: [{"role": "string", "text": "string"}, ...]
        Also delete message with role "system"
        '''
        try:
            formatted_messages = []
            for message in messages:
                if message['role'] == 'system':
                    continue
                role = "Ассистент" if message['role'] == 'assistant' else message['role']
                formatted_messages.append({"role": role, "text": message['content']})
            return formatted_messages
        except Exception as e:
            logger.exception('Could not format messages for Yandex API')
            raise Exception('Could not format messages for YandexGPT API')
        
    async def summary(self, text, size=240):
        '''
        Make summary of text
        Input text and size of summary (in tokens)
        '''
        # Get a summary prompt
        instructionText =  f'You are very great at summarizing text to fit in {size//30} sentenses. Answer with summary only.'
        requestText = 'Make a summary:\n' + str(text)
        # make post request to Yandex API
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Api-Key {self.chat_vars['SecretKey']}",
            'x-folder-id': self.chat_vars['CatalogID']
        }
        payload = {
            "model": self.chat_vars['Model'],
            "generationOptions": {
                "partialResults": self.chat_vars['PartialResults'],
                "temperature": self.chat_vars['Temperature'],
                "maxTokens": size
            },
            "instructionText": instructionText,
            "requestText": requestText
        }
        response = self.requests.post(self.chat_vars['InstructEndpoint'] , json=payload, headers=headers)
        # log to logger file fact of message being sent
        logger.debug('Summary request was sent to Yandex API')
        # check if response is successful
        if response.status_code != 200:
            logger.error('Could not send summary request to Yandex API')
            return None, None
        # get response from Yandex API
        response = response.json()
        completion_tokens = int(response['alternatives']['numTokens']) if response['alternatives']['numTokens'] else None
        prompt_tokens = int(response['numPromptTokens']) if response['numPromptTokens'] else None
        response = str(response['alternatives']['text']) if response['alternatives']['text'] else None
        # log to logger file fact of message being received
        logger.debug('Summary request was received from Yandex API')
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
    
    async def count_tokens(self, messages, model='gpt-3.5-turbo'):
        '''
        Count tokens in messages via tiktoken
        '''
        try:
            # Get the encoding for the model
            encoding = tiktoken.encoding_for_model(model)
            # Count the number of tokens
            tokens = 0
            for message in messages:
                text = message['role'] + ': ' + message['content']
                tokens += len(encoding.encode(text))
            logger.debug(f'Messages were counted for tokens: {tokens}')
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
    
    
class AnthropicEngine:
    def __init__(self, text=False, speech=False):
        '''
        Initialize Anthropic API for text generation
        Available: text generation, speech2text
        '''
        from anthropic import AsyncAnthropic
        import anthropic 
        self.anthropic = anthropic
        import configparser
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
            })
        self.config.read('./data/.config')   
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
        self.text_initiation, self.speech_initiation = text, speech
        self.text_init() if self.text_initiation else None

        self.image_generation = False
        self.function_calling = False

        logger.info('Anthropic Engine was initialized')

    def text_init(self):
        '''
        Initialize text generation
        '''
        self.model = self.config.get("Anthropic", "ChatModel")
        self.model_completion_price = float(self.config.get("Anthropic", "ChatModelCompletionPrice")) 
        self.model_prompt_price = float(self.config.get("Anthropic", "ChatModelPromptPrice")) 
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

        self.vision = self.config.getboolean("Anthropic", "Vision")
        self.image_size = int(self.config.get("Anthropic", "ImageSize")) 
        if self.vision:
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
            new_messages = []
            system_prompt = ""
            if messages is None:
                return system_prompt, None
            logger.debug(f'Messages to revise for Anthropic: {len(messages)}')
            # first message must use the "user" role
            # roles must alternate between "user" and "assistant", but found multiple "assistant" roles in a row
            # itterate over messages
            i = 0
            for i in range(len(messages)):
                message = messages[i]
                if message['role'] == 'system':
                    system_prompt += f"{message['content']}\n"
                    continue
                
                # TODO: optimize this part
                if len(new_messages) == 0 and message['role'] != 'user':
                    new_messages.append({"role": "user", "content": "<start>"})
                last_role = new_messages[-1]['role'] if len(new_messages) > 0 else 'None'
                if message['role'] == last_role and type(message['content']) == str:
                    new_messages[-1]['content'] += '\n' + message['content']
                    continue

                if message['role'] == 'user' and self.vision:
                    if type(message['content']) == list:
                        if last_role == 'user' and type(new_messages[-1]['content']) == list:
                            pass
                        else:
                            new_messages.append({
                                "role": "user",
                                "content": []
                            })
                        for item in message['content']:
                            if item['type'] == 'text':
                                new_messages[-1]['content'].append({
                                    "type": "text",
                                    "text": item['text'],
                                })
                            elif item['type'] == 'image':
                                image_url = str(item['image_url']['url']).replace('data:image/jpeg;base64,', '')
                                new_messages[-1]['content'].append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": image_url,
                                    }
                                })
                        logger.debug(f'Image was added to message for Anthropic')
                        continue
                new_messages.append(message)
            return system_prompt, new_messages
        except Exception as e:
            logger.error(f'Could not revise messages for Anthropic: {e}')
            return "", None
        
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
        if self.text_initiation == False:
            return None, None, None
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
                return 'It seems that chat session is too long or something else happened. You can try to /delete session and start a new one.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
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

    async def count_tokens(self, messages, model='gpt-3.5-turbo'):
        '''
        Count tokens in messages via tiktoken
        ! ALGORITHM IS NOT ACCURATE AND USED JUST FOR ESTIMATION !
        '''
        try:
            # Get the encoding for the model
            encoding = tiktoken.encoding_for_model(model)
            # Count the number of tokens
            tokens = 0
            for message in messages:
                # Check if there is images in message and leave only text
                if self.vision:
                    message, trimmed = await self.leave_only_text(message)
                text = message['role'] + ': ' + message['content']
                tokens += len(encoding.encode(text))
            logger.debug(f'Messages were counted for tokens: {tokens}')
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
        
    async def leave_only_text(self, message):
        '''
        Leave only text in message with images
        '''
        if message is None:
            return None, False
        try:
            message_copy = message.copy()
            # Check if there is images in message
            trimmed = False
            if 'content' in message_copy and type(message_copy['content']) == list:
                # Leave only text in message
                for i in range(len(message_copy['content'])):
                    if message_copy['content'][i]['type'] == 'text':
                        message_copy['content'] = message_copy['content'][i]['text']
                        trimmed = True
                        break
            return message_copy, trimmed
        except Exception as e:
            logger.exception('Could not leave only text in message')
            return message, False
        
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
                    if message_copy['content'][i]['type'] == 'image':
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
                text, trimmed = await self.leave_only_text(messages[i])
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
        

####### TEST #######
if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)

    # engine = OpenAIEngine(text=True)
    # engine = YandexEngine(text=True)
    engine = AnthropicEngine(text=True)

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