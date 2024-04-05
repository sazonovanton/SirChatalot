# Description: Chats processing class

import configparser
config = configparser.ConfigParser()
config.read('./data/.config', encoding='utf-8')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-Processing")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/sirchatalot.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7,
                                       encoding='utf-8')
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import pickle
import os
from pydub import AudioSegment
from datetime import datetime

# Support: OpenAI API, YandexGPT API, Claude API
from chatutils.engines import OpenAIEngine, YandexEngine, AnthropicEngine

class ChatProc:
    def __init__(self, text="OpenAI", speech="OpenAI") -> None:
        self.speech_engine = None
        text = text.lower()
        speech = speech.lower() if speech is not None else None
        self.max_tokens = 2000
        self.summarize_too_long = False
        self.log_chats = config.getboolean("Logging", "LogChats") if config.has_option("Logging", "LogChats") else False
        self.model_prompt_price, self.model_completion_price = 0, 0
        self.audio_format, self.s2t_model_price = ".wav", 0
        if text == "openai":
            self.text_engine = OpenAIEngine(text=True)
        elif text == "yagpt" or text == "yandexgpt" or text == "yandex":
            self.text_engine = YandexEngine(text=True)
        elif text == "claude" or text == "anthropic":
            self.text_engine = AnthropicEngine(text=True)
        else:
            logger.error("Unknown text engine: {}".format(text))
            raise Exception("Unknown text engine: {}".format(text))
        
        self.model_prompt_price = self.text_engine.model_prompt_price
        self.model_completion_price = self.text_engine.model_completion_price
        self.max_tokens = self.text_engine.max_tokens
        self.summarize_too_long = self.text_engine.summarize_too_long
        
        self.vision = self.text_engine.vision
        if self.vision:
            self.image_size = self.text_engine.image_size
            if self.image_size is None:
                self.image_size = 512
            self.pending_images = {}

        self.image_generation = False
        self.image_generation_engine_name = None
        self.image_engine = None
        if config.has_section("ImageGeneration"):
            self.image_generation = True
        if not self.image_generation and config.has_section("OpenAI"):
            self.image_generation = config.getboolean("OpenAI", "ImageGeneration") if config.has_option("OpenAI", "ImageGeneration") else False
        if self.image_generation:
            self.load_image_generation()
            logger.debug(f'Image generation is enabled, price: ${self.image_generation_price}, size: {self.image_generation_size}, style: {self.image_generation_style}, quality: {self.image_generation_quality}')

        self.function_calling = self.text_engine.function_calling
        if self.function_calling:
            self.load_function_calling(text)
            self.text_engine.function_calling_tools = self.function_calling_tools
            logger.debug(f'Function calling is enabled')

        if self.speech_engine is not None:
            if speech == "openai":
                self.speech_engine = OpenAIEngine(speech=True)
                self.audio_format = self.speech_engine.audio_format
                self.s2t_model_price = self.speech_engine.s2t_model_price
            else:
                logger.error("Unknown speech2text engine: {}".format(speech))
                raise Exception("Unknown speech2text engine: {}".format(speech))
        
        self.system_message = self.text_engine.system_message 
        print('System message:', self.system_message)
        print('-- System message is used to set personality to the bot. It can be changed in the self.config file.\n')
        if self.summarize_too_long:
            print('-- Summarize too long is set to True. It means that if the text is too long, then it will be summarized instead of trimmed.\n')

        self.file_summary_tokens = int(config.get("Files", "MaxSummaryTokens")) if config.has_option("Files", "MaxSummaryTokens") else (self.max_tokens // 2)
        self.max_file_length = int(config.get("Files", "MaxFileLength")) if config.has_option("Files", "MaxFileLength") else 10000

        # load chat history from file
        self.chats_location = "./data/tech/chats.pickle"
        self.chats = self.load_pickle(self.chats_location)
        # load statistics from file
        self.stats_location = "./data/tech/stats.pickle"
        self.stats = self.load_pickle(self.stats_location)

        if self.log_chats:
            logger.info('* Chat history is logged *')

    def load_function_calling(self, text):
        '''
        Load function calling tools
        '''
        if text == "openai":
            from chatutils.tools_config import OpenAIConfig as tools_config
        self.webengine = None
        self.urlopener = None
        self.available_functions = {}
        self.function_calling_tools = []
        if self.image_generation:
            self.available_functions["generate_image"] = self.image_engine.generate_image
            self.function_calling_tools.append(tools_config.image_generation)
        if 'Web' in config:
            if config.has_option("Web", "SearchEngine"):
                if str(config.get("Web", "SearchEngine")).lower() == "google":
                    from chatutils.web_engines import GoogleEngine
                    self.webengine = GoogleEngine()
                    logger.debug(f'Web search engine is set to Google')
                    self.available_functions["web_search"] = self.webengine.search
                    self.function_calling_tools.append(tools_config.web_search)
            if config.has_option("Web", "UrlOpen"):
                if config.getboolean("Web", "UrlOpen"):
                    from chatutils.web_engines import URLOpen
                    self.urlopener = URLOpen()
                    self.url_summary = config.getboolean("Web", "URLSummary") if config.has_option("Web", "URLSummary") else False
                    logger.debug(f'URL opener is enabled, URL summary is set to {self.url_summary}')
                    self.available_functions["url_opener"] = self.urlopener.open_url
                    self.function_calling_tools.append(tools_config.url_opener)

    def load_image_generation(self):
        '''
        Load image generation engine
        '''
        if config.has_section("ImageGeneration"):
            if config.has_option("ImageGeneration", "Engine"):
                if config.get("ImageGeneration", "Engine").lower() in ["openai", "dall-e", "dalle"]:
                    # OpenAI DALL-E
                    from chatutils.image_engines import DalleEngine
                    self.image_generation_engine_name = "dalle"
                    if config.has_option("ImageGeneration", "APIKey"):
                        api_key = config.get("ImageGeneration", "APIKey")
                    elif config.has_option("OpenAI", "SecretKey"):
                        api_key = config.get("OpenAI", "SecretKey")
                    else:
                        logger.error("No API key provided for image generation")
                        raise Exception("No API key provided for image generation")
                    if config.has_option("ImageGeneration", "BaseURL"):
                        base_url = config.get("ImageGeneration", "BaseURL")
                    elif config.has_option("OpenAI", "BaseURL"):
                        base_url = config.get("OpenAI", "BaseURL")
                    else:
                        base_url = None
                    if base_url == 'None':
                        base_url = None
                    self.image_engine = DalleEngine(api_key, base_url)
                elif config.get("ImageGeneration", "Engine").lower() in ["stability"]:
                    # OpenAI Stability
                    from chatutils.image_engines import StabilityEngine
                    self.image_generation_engine_name = "stability"
                    if config.has_option("ImageGeneration", "APIKey"):
                        api_key = config.get("ImageGeneration", "APIKey")
                    else:
                        logger.error("No API key provided for image generation")
                        raise Exception("No API key provided for image generation")
                    self.image_engine = StabilityEngine(api_key)
                else:
                    logger.error(f"Unknown image generation engine {config.get('ImageGeneration', 'Engine')}")
                    raise Exception(f"Unknown image generation engine {config.get('ImageGeneration', 'Engine')}")
            else:
                logger.error("No image generation engine provided")
                raise Exception("No image generation engine provided")
        elif config.has_section("OpenAI"):
            if config.has_option("OpenAI", "ImageGeneration"):
                if config.getboolean("OpenAI", "ImageGeneration"):
                    # OpenAI DALL-E
                    from chatutils.image_engines import DalleEngine
                    if config.has_option("OpenAI", "SecretKey"):
                        api_key = config.get("OpenAI", "SecretKey")
                    else:
                        logger.error("No API key provided for image generation (deprecated)")
                        raise Exception("No API key provided for image generation (deprecated)")
                    if config.has_option("OpenAI", "BaseURL"):
                        base_url = config.get("OpenAI", "BaseURL")
                    else:
                        base_url = None
                    if base_url == 'None':
                        base_url = None
                    self.image_engine = DalleEngine(api_key, base_url)
                else:
                    logger.debug("Image generation is disabled (deprecated) - Parameter is set to False")
            else:
                logger.debug("Image generation is disabled (deprecated) - No parameter provided")
        else:
            logger.debug("Image generation is disabled (deprecated) - No config provided")

        self.image_generation_size = self.image_engine.settings["ImageGenerationSize"]
        self.image_generation_style = self.image_engine.settings["ImageGenerationStyle"]
        self.image_generation_quality = self.image_engine.settings["ImageGenerationQuality"]
        self.image_generation_price = self.image_engine.settings["ImageGenerationPrice"]

    async def speech_to_text(self, audio_file):
        '''
        Convert speech to text
        Input file with speech
        '''
        if self.speech_engine is None:
            return None
        try:
            transcript = await self.speech_engine.speech_to_text(audio_file)
            transcript += ' (it was a voice message transcription)'
        except Exception as e:
            logger.error('Could not convert voice to text')
            transcript = None
        if transcript is not None:
            # add statistics
            try:
                audio = AudioSegment.from_wav(audio_file.replace('.ogg', self.audio_format))
            except Exception as e:
                logger.error('Could not get audio duration: ' + str(audio_file))
                audio = None
            self.add_stats(id=id, speech2text_seconds=audio.duration_seconds)
        # delete audio file
        try:
            audio_file = str(audio_file)
            os.remove(audio_file.replace('.ogg', self.audio_format))
            logger.debug('Audio file ' + audio_file.replace('.ogg', self.audio_format) + ' was deleted (converted)')
        except Exception as e:
            logger.error('Could not delete converted audio file: ' + str(audio_file))
        return transcript
    
    async def chat_voice(self, id=0, audio_file=None):
        '''
        Chat with GPT using voice
        Input id of user and audio file
        '''
        try:
            if self.speech_engine is None:
                logger.error('No speech2text engine provided')
                return 'Sorry, speech-to-text is not available.'
            # convert voice to text
            if audio_file is not None:
                transcript = await self.speech_to_text(audio_file)
            else:
                logger.error('No audio file provided for voice chat')
                return None
            if transcript is None:
                logger.error('Could not convert voice to text')
                return 'Sorry, I could not convert your voice to text.'
            response = await self.chat(id=id, message=transcript)
            return response
        except Exception as e:
            logger.exception('Could not voice chat with GPT')
            return None
        
    async def add_image(self, id, image_b64):
        '''
        Add image to the chat
        Input id of user and image in base64
        '''
        try:
            if self.vision is False:
                logger.error('Vision is not available')
                return False
            
            # Check if there is a chat
            new_chat = False
            if id not in self.chats:
                # If there is no chat, then create it
                success = await self.init_style(id=id)
                if not success:
                    logger.error('Could not init style for user: ' + str(id))
                    return False
                new_chat = True

            messages = self.chats[id]
            messages.append({
                "role": "user", 
                "content": [
                    {
                        "type": "image",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        },
                    }
                ] 
            })
            # Add flag that there is an image without caption
            self.pending_images[id] = True
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not add image to chat for user: ' + str(id))
            return False
        
    async def add_caption(self, id, caption):
        '''
        Add caption to the image
        Input id of user and caption
        '''
        try:
            if self.vision is False:
                logger.error('Vision is not available')
                return False
            
            # Check if there is a chat
            if id not in self.chats:
                logger.error('Could not add caption to image. No chat for user: ' + str(id))
                return False
            
            messages = self.chats[id]
            # check if there is an image without caption
            if id not in self.pending_images:
                return False
            # remove flag that there is an image without caption
            del self.pending_images[id]
            # add caption to the last image
            messages[-1]['content'].append({
                "type": "text",
                "text": caption,
            })
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not add caption to image for user: ' + str(id))
            return False
        
    async def init_style(self, id=0, style=None):
        '''
        Init style of chat
        Create chat history if it does not exist
        Input:
            * id - id of user
            * style - style of chat (default: None)
        '''         
        try:   
            # get chat history
            if style is None:
                style = self.system_message
            # if vision is enabled, then add information about it
            if self.vision:
                style += '\n# You have vision capabilities enabled, it means that you can see images in chat'
            # get messages if chat exists
            if id in self.chats:
                messages = self.chats[id]
            else:
                messages = [{"role": "system", "content": style}]
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not init style for user: ' + str(id))
            return False
        
    async def add_to_chat_history(self, id=0, message=None):
        '''
        Add message to chat history
        Input:
            * id - id of user
            * message - message to add to chat history (JSON format: {"role": "user", "content": "message"})
        '''
        try:
            if id not in self.chats:
                # If there is no chat, then create it
                success = await self.init_style(id=id)
                if not success:
                    logger.error('Could not init style for user: ' + str(id))
                    return False
            messages = self.chats[id]
            messages.append(message)
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.error(f'Could not add message to chat history for user {id}: {e}')
            return False
        
    async def save_chat(self, id=0, messages=None):
        '''
        Save chat history
        Input id of user and messages
        '''
        try:
            if messages is None:
                logger.error('Could not save chat history. No messages provided')
                return False
            if id not in self.chats:
                # If there is no chat, then create it
                success = await self.init_style(id=id)
                if not success:
                    logger.error('Could not init style for user: ' + str(id))
                    return False
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            logger.debug(f'Chat history for user {id} was saved successfully')
            return True
        except Exception as e:
            logger.error(f'Could not save chat history for user {id}: {e}')
            return False
        
    async def count_tokens(self, messages):
        '''
        Count tokens in messages
        Input messages
        '''
        return await self.text_engine.count_tokens(messages)
    
    async def chat_summary(self, messages):
        '''
        Chat with GPT to summarize messages
        Input messages
        '''
        return await self.text_engine.chat_summary(messages)

    async def trim_messages(self, messages, trim_count=1):
        '''
        Trim messages (delete first trim_count messages)
        Do not trim system message (role == 'system', id == 0)
        '''
        try:
            if messages is None or len(messages) <= 1:
                logger.warning('Could not trim messages')
                return None
            system_message = messages[0] if messages[0]['role'] == 'system' else {"role": "system", "content": self.system_message}
            messages = messages[1:] if messages[0]['role'] == 'system' else messages
            logger.debug(f'Deleting messages: {messages[:trim_count]}')
            messages = messages[trim_count:]
            messages.insert(0, system_message)
            return messages
        except Exception as e:
            logger.error(f'Could not trim messages: {e}')
            return None
        
    async def summarize_messages(self, messages, leave_messages=2):
        '''
        Summarize messages (leave only last leave_messages messages)
        Do not summarize system message (role == 'system', id == 0)
        '''
        try:
            if messages is None or len(messages) <= leave_messages:
                logger.warning('Could not summarize messages')
                return None
            system_message = messages[0] if messages[0]['role'] == 'system' else {"role": "system", "content": self.system_message}
            last_messages = messages[-leave_messages:]
            logger.debug(f'Summarizing {len(messages)} messages, leaving only {len(last_messages)} last messages')
            messages = messages[1:-leave_messages] if messages[0]['role'] == 'system' else messages[:-leave_messages]
            # summarize messages
            summary, token_usage = await self.chat_summary(messages)
            messages = []
            messages.append(system_message)
            messages.append({
                "role": "assistant",
                "content": f"<Previous conversation summary: {summary}>"
            })
            for message in last_messages:
                messages.append(message)
            logger.debug(f'Summarized messages to {len(messages)} messages, token usage: {token_usage}')
            return messages, token_usage
        except Exception as e:
            logger.error(f'Could not summarize messages: {e}')
            return None, {"prompt": 0, "completion": 0}

    async def chat(self, id=0, message="Hi! Who are you?", style=None):
        '''
        Chat with GPT
        Input:
            * id - id of user
            * message - message to chat with GPT
            * style - style of chat (default: None)
        '''
        try:
            prompt_tokens, completion_tokens = 0, 0
            # Init style if it is not set
            if id not in self.chats:
                success = await self.init_style(id=id, style=style)
                if not success:
                    logger.error('Could not init style for user: ' + str(id))
                    return 'Sorry, I could not init style for you.'
            # get messages
            messages = self.chats[id]
            # If there is an image without caption, then add caption
            if self.vision and id in self.pending_images:
                self.chats[id] = messages
                await self.add_caption(id, message)
                messages = self.chats[id]
            else:
                # Add message to the chat
                # messages.append({"role": "user", "content": message})
                await self.add_to_chat_history(id=id, message={"role": "user", "content": message})
            # Trim or summarize messages if they are too long
            messages_tokens = await self.count_tokens(messages)
            if messages_tokens is None:
                messages_tokens = 0
            if messages_tokens > self.max_tokens:
                if not self.summarize_too_long:
                    while await self.count_tokens(messages) > int(self.max_tokens*0.8):
                        messages = await self.trim_messages(messages)
                else:
                    messages, token_usage = await self.summarize_messages(messages)
                    prompt_tokens += int(token_usage['prompt'])
                    completion_tokens += int(token_usage['completion'])
                if messages is None:
                    return 'There was an error due to a long conversation. Please, contact the administrator or /delete your chat history.'

            # Wait for response
            response, messages, token_usage = await self.text_engine.chat(id=id, messages=messages)
            # add statistics
            if token_usage is not None:
                prompt_tokens += int(token_usage['prompt'])
                completion_tokens += int(token_usage['completion'])
            # TODO: check if function was called
            if self.function_calling:
                if type(response) == tuple:
                    if response[0] == 'function':
                        function_name, function_args = response[1], response[2]
                        logger.debug(f'Function was called: "{function_name}" with arguments: "{function_args}"')
                        if response[1] == 'generate_image':
                            # call function to generate image
                            function_to_call = self.available_functions[function_name]
                            function_response = await function_to_call(
                                prompt = function_args.get("prompt"),
                                image_orientation = function_args.get("image_orientation"),
                                image_style = function_args.get("image_style"),
                            )
                            image, text = function_response[0], function_response[1]
                            if image is not None:
                                # add to chat history
                                await self.add_to_chat_history(
                                    id=id, 
                                    message={"role": "function", "name": function_name, "content": str(text)}
                                    )
                                # add statistics
                                await self.add_stats(id=id, images_generated=1)
                                response = ('image', image, text)
                            elif image is None and text is not None:
                                response = f'Image was not generated. {text}'
                                await self.add_to_chat_history(
                                    id=id, 
                                    message={"role": "assistant", "content": response}
                                    )
                            else:
                                response = 'Sorry, something went wrong.'
                                logger.error(f'Function was called, but image was not generated: {response}')
                        elif response[1] == 'web_search':
                            # call function to search the web
                            function_to_call = self.available_functions[function_name]
                            function_response = await function_to_call(
                                query = function_args.get("query"),
                            )
                            if function_response is None:
                                function_response = 'Error while searching the web'
                            await self.add_to_chat_history(
                                id=id, 
                                message={"role": "function", "name": function_name, "content": str(function_response)}
                                )
                            # Push response to LLM again
                            messages = self.chats[id]
                            logger.debug(f'Pushing response to LLM again: {function_response}')
                            response, messages, token_usage = await self.text_engine.chat(id=id, messages=messages)
                            # add statistics
                            if token_usage is not None:
                                prompt_tokens += int(token_usage['prompt'])
                                completion_tokens += int(token_usage['completion'])
                            if response is None:
                                response = 'Sorry, I could not get an answer to your message. Please try again or contact the administrator.'
                            else:
                                await self.save_chat(id=id, messages=messages)
                        elif response[1] == 'url_opener':
                            # call function to open URL
                            function_to_call = self.available_functions[function_name]
                            function_response = await function_to_call(
                                url = function_args.get("url"),
                            )
                            if function_response is None:
                                function_response = 'Error while opening the URL or there was no content'
                            elif self.url_summary:
                                # create summary of the content
                                logger.debug(f'Attempting to summarize the content of the URL ({len(function_response)})')
                                function_response, token_usage = await self.text_engine.summary(f'User message: {message}. Text from URL: {function_response}')
                                if function_response is None:
                                    function_response = 'Error while summarizing the content of the URL'
                                else:
                                    prompt_tokens += int(token_usage['prompt'])
                                    completion_tokens += int(token_usage['completion'])
                            else:
                                pass
                            await self.add_to_chat_history(
                                id=id, 
                                message={"role": "function", "name": function_name, "content": f"URL content: {function_response}"}
                                )
                            # Push response to LLM again
                            messages = self.chats[id]
                            logger.debug(f'Pushing response of URL opener to LLM again: {function_response}')
                            response, messages, token_usage = await self.text_engine.chat(id=id, messages=messages)
                            # add statistics
                            if token_usage is not None:
                                prompt_tokens += int(token_usage['prompt'])
                                completion_tokens += int(token_usage['completion'])
                            if response is None:
                                response = 'Sorry, I could not get an answer to your message. Please try again or contact the administrator.'
                            else:
                                await self.save_chat(id=id, messages=messages)
            else:
                # save chat history
                await self.save_chat(id=id, messages=messages)
            # add statistics
            await self.add_stats(id=id, prompt_tokens_used=prompt_tokens, completion_tokens_used=completion_tokens)
            return response
        except Exception as e:
            logger.exception('Could not get answer to message: ' + message + ' from user: ' + str(id))
            return 'Sorry, I could not get an answer to your message. Please try again or contact the administrator.'
        
    async def imagine(self, id=0, prompt=None, add_to_chat=True):
        '''
        Generate image from text
        Input: 
            * id - id of user
            * prompt - text for image generation (add --revision to display revised prompt)
            * size - size of image 
            * style - style of image
            * quality - quality of image
            * add_to_chat - add information about image to chat history (default: True)
        '''
        try:
            if self.image_generation == False:
                logger.error('Image generation is not available')
                return 'Sorry, image generation is not available.'
            if prompt is None:
                logger.error('No prompt provided for image generation')
                return 'Sorry, I could not generate an image without a prompt.'
            # generate image    
            revision = False        
            if '--revision' in prompt:
                prompt = prompt.replace('--revision', '')
                revision = True
            image, text = await self.image_engine.imagine(prompt=prompt, id=0, revision=True)
            if image is not None:
                # add statistics
                await self.add_stats(id=id, images_generated=1)
                # add information to history
                if add_to_chat:
                    await self.add_to_chat_history(
                        id=id, 
                        message={"role": "assistant", "content": f"<system - image was generated from the prompt: {text}>"}
                    )
                # add text to chat if it is not None
                if revision:
                    text = 'Revised prompt: ' + text
                else:
                    text = None
            if image is None and text is None:
                logger.error('Could not generate image from prompt: ' + prompt)
                return 'Sorry, I could not generate an image from your prompt.'
            # return image
            return image, text
        except Exception as e:
            logger.exception('Could not generate image from prompt: ' + prompt + ' for user: ' + str(id))
            return None, 'Sorry, I could not generate an image from your prompt.'
            
    def load_pickle(self, filepath):
        '''
        Load pickle file if exists or create new 
        '''
        try:
            payload = pickle.load(open(filepath, "rb")) 
            return payload
        except Exception as e:
            payload = {}
            pickle.dump(payload, open(filepath, "wb"))
            logger.debug(f'Could not load file: {filepath}. Created new file.')
            return payload
        
    async def add_stats(self, id=None, speech2text_seconds=None, messages_sent=None, voice_messages_sent=None, prompt_tokens_used=None, completion_tokens_used=None, images_generated=None):
        '''
        Add statistics (tokens used, messages sent, voice messages sent) by user
        Input:
            * id - id of user
            * speech2text_seconds - seconds used for speech2text
            * messages_sent - messages sent
            * voice_messages_sent - voice messages sent
            * prompt_tokens_used - tokens used for prompt
            * completion_tokens_used - tokens used for completion
            * images_generated - images generated
        '''
        try:
            if id is None:
                logger.debug('Could not add stats. No ID provided')
                return None
            if id not in self.stats:
                self.stats[id] = {'Tokens used': 0, 'Speech to text seconds': 0, 'Messages sent': 0, 'Voice messages sent': 0, 'Prompt tokens used': 0, 'Completion tokens used': 0, 'Images generated': 0}
            self.stats[id]['Messages sent'] += messages_sent if messages_sent is not None else 0
            if self.speech_engine:
                self.stats[id]['Speech to text seconds'] += round(speech2text_seconds) if speech2text_seconds is not None else 0
                self.stats[id]['Voice messages sent'] += voice_messages_sent if voice_messages_sent is not None else 0
            self.stats[id]['Prompt tokens used'] += prompt_tokens_used if prompt_tokens_used is not None else 0
            self.stats[id]['Completion tokens used'] += completion_tokens_used if completion_tokens_used is not None else 0
            if self.image_generation:
                self.stats[id]['Images generated'] += images_generated if images_generated is not None else 0
            # save statistics to file (unsafe way)
            pickle.dump(self.stats, open(self.stats_location, "wb"))
        except KeyError as e:
            logger.error('Could not add statistics for user: ' + str(id))
            # add key to stats and try again
            current_stats = self.stats[id]
            key_missing = str(e).split('\'')[1]
            current_stats[key_missing] = 0
            self.stats[id] = current_stats
            try:
                pickle.dump(self.stats, open(self.stats_location, "wb"))
            except Exception as e:
                logger.error('Could not add statistics for user after adding keys: ' + str(id))
        except Exception as e:
            logger.error('Could not add statistics for user: ' + str(id))

    async def get_stats(self, id=None, counter=0):
        '''
        Get statistics (tokens used, speech2text in seconds used, messages sent, voice messages sent) by user
        Input: 
            * id - id of user
        '''
        try:
            # get statistics by user
            if id is None:
                logger.debug('Get statistics - ID was not provided')
                return None
            if id in self.stats:
                statisitics = ''
                cost = 0
                for key, value in self.stats[id].items():
                    if key in ['Tokens used', 'Speech2text seconds']:
                        continue # deprecated values to ignore (for backward compatibility)
                    if self.image_generation == False:
                        if key == 'Images generated':
                            continue
                    if self.speech_engine is None:
                        if key in ['Speech to text seconds', 'Voice messages sent']:
                            continue
                    statisitics += key + ': ' + str(value) + '\n'
                if self.speech_engine:
                    cost += self.stats[id]['Speech to text seconds'] / 60 * self.s2t_model_price
                cost += self.stats[id]['Prompt tokens used'] / 1000 * self.model_prompt_price 
                cost += self.stats[id]['Completion tokens used'] / 1000 * self.model_completion_price
                if self.image_generation:
                    cost += self.stats[id]['Images generated'] * self.image_generation_price
                statisitics += '\nAppoximate cost of usage is $' + str(round(cost, 2))
                return statisitics
            return None
        except KeyError as e:
            logger.error(f'Could not get statistics for user {id} due to missing key: {e}')
            # add key to stats and try again
            current_stats = self.stats[id]
            key_missing = str(e).split('\'')[1]
            current_stats[key_missing] = 0
            self.stats[id] = current_stats
            try:
                pickle.dump(self.stats, open(self.stats_location, "wb"))
            except Exception as e:
                logger.error(f'Could not get statistics for user {id} after adding keys: {e}')
            if counter > 6:
                return 'There was an error while getting statistics. Please, try again.'
            return await self.get_stats(id=id, counter=counter+1) # recursive call
        except Exception as e:
            logger.error(f'Could not get statistics for user {id}: {e}')
            return None
        
    async def dump_chat(self, id=None, plain=False, chatname=None) -> bool:
        '''
        Dump chat to a file
        If plain is True, then dump chat as plain text with roles and messages
        If plain is False, then dump chat as pickle file
        '''
        try:
            logger.debug('Dumping chat for user: ' + str(id))
            if id is None:
                logger.debug('Could not dump chat. No ID provided')
                return False
            if id not in self.chats:
                return False
            if chatname is None:
                chatname = datetime.now().strftime("%Y%m%d-%H%M%S")
            messages = self.chats[id]
            if plain:
                # dump chat to a file
                with open(f'./data/chats/{id}_{chatname}.txt', 'w') as f:
                    for message in messages:
                        f.write(message['role'] + ': ' + message['content'] + '\n')
            else:
                # dump chat to user file
                filename = f'./data/chats/{id}.pickle'
                chats = self.load_pickle(filename)
                chats[chatname] = messages
                pickle.dump(chats, open(filename, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not dump chat for user: ' + str(id))
            return False
        
    async def delete_chat(self, id=0) -> bool:
        '''
        Delete chat history
        Input id of user
        '''
        try:
            if id not in self.chats:
                return False
            if self.log_chats:
                await self.dump_chat(id=id, plain=True)
            del self.chats[id]
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not delete chat history for user: ' + str(id))
            return False

    async def stored_sessions(self, id=None):
        '''
        Get list of stored sessions for user
        '''
        try:
            if id is None:
                logger.debug('Could not get stored chats. No ID provided')
                return False
            if id not in self.chats:
                return False
            sessions = pickle.load(open("./data/chats/" + str(id) + ".pickle", "rb"))
            # sessions names (dict keys)
            names = list(sessions.keys())
            return names
        except Exception as e:
            logger.exception('Could not get stored chats for user: ' + str(id))
            return False
        
    async def load_session(self, id=None, chatname=None):
        '''
        Load chat session by name for user, overwrite chat history with session
        '''
        try:
            if id is None:
                logger.debug('Could not load chat. No ID provided')
                return False
            if chatname is None:
                logger.debug('Could not load chat. No chatname provided')
                return False
            sessions = pickle.load(open("./data/chats/" + str(id) + ".pickle", "rb"))
            messages = sessions[chatname]
            # overwrite chat history
            self.chats[id] = messages
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not load session for user: ' + str(id))
            return False

    async def delete_session(self, id=0, chatname=None):
        '''
        Delete chat session by name for user
        '''
        try:
            if id is None:
                logger.debug('Could not load chat. No ID provided')
                return False
            if chatname is None:
                logger.debug('Could not load chat. No chatname provided')
                return False
            sessions = pickle.load(open("./data/chats/" + str(id) + ".pickle", "rb"))
            del sessions[chatname]
            pickle.dump(sessions, open("./data/chats/" + str(id) + ".pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not delete session for user: ' + str(id))
            return False
        
    async def change_style(self, id=0, style=None):
        '''
        Change style of chat
        Input id of user and style
        '''         
        try:   
            # get chat history
            if style is None:
                style = self.system_message
            # get messages if chat exists
            if id in self.chats:
                messages = self.chats[id]
            else:
                messages = [{"role": "system", "content": style}]
            # change style
            if messages[0]['role'] == 'system':
                messages[0]['content'] = style 
            else:
                messages.insert(0, {"role": "system", "content": style})
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not change style for user: ' + str(id))
            return False

    async def filechat(self, id=0, text='', sumdepth=3):
        '''
        Process file 
        Input id of user and text
        '''
        try:
            # check length of text
            # if text length is more than self.max_file_length then return message
            if len(text) > self.max_file_length:
                return 'Text is too long. Please, send a shorter text.'
            # if text is than self.max_tokens // 2, then make summary
            maxlength = round(self.file_summary_tokens) * 4 - 32
            if len(text) > maxlength:
                # to do that we split text into chunks with length no more than maxlength and make summary for each chunk
                # do that until we have summary with length no more than maxlength
                depth = 0
                chunklength = self.max_tokens * 4 - 80
                while len(text) > maxlength:
                    if depth == sumdepth:
                        # cut text to maxlength and return
                        text = text[:maxlength]
                        break
                    depth += 1
                    chunks = [text[i:i+chunklength] for i in range(0, len(text), chunklength)]
                    text = ''
                    for chunk in chunks:
                        text += await self.text_engine.summary(chunk, size=self.file_summary_tokens) + '\n'
                text = '# Summary from recieved file: #\n' + text
            else:
                # if text is shorter than self.max_tokens // 2, then do not make summary
                text = '# Text from recieved file: #\n' + text
            # chat with GPT
            response = self.chat(id=id, message=text)
            return response
        except Exception as e:
            logger.exception('Could not process file for user: ' + str(id))
            return None

