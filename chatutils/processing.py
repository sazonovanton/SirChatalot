# Description: Chats processing class

from chatutils.misc import setup_logging, read_config
config = read_config('./data/.config')
logger = setup_logging(logger_name='SirChatalot-Processing', log_level=config.get('Logging', 'LogLevel', fallback='WARNING'))

import pickle
import os
from pydub import AudioSegment
from datetime import datetime

from chatutils.audio_engines import get_audio_engine
from chatutils.text_engines import get_text_engine
from chatutils.responses import ErrorResponses as er
from chatutils.datatypes import Message, FunctionResponse

class ChatProc:
    def __init__(self) -> None:
        self.max_tokens = 2000
        self.summarize_too_long = False
        self.log_chats = config.getboolean("Logging", "LogChats", fallback=False)
        self.model_prompt_price, self.model_completion_price = 0, 0
        self.text_engine = get_text_engine(config.get("Telegram", "TextEngine", fallback="openai"))
        
        self.model_prompt_price = self.text_engine.model_prompt_price
        self.model_completion_price = self.text_engine.model_completion_price
        self.max_tokens = self.text_engine.max_tokens
        self.summarize_too_long = self.text_engine.summarize_too_long
        self.trim_size = self.text_engine.trim_size
        self.trim_too_long = self.text_engine.trim_too_long
        
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
            self.image_generation = config.getboolean("OpenAI", "ImageGeneration", fallback=False)
        if self.image_generation:
            self.load_image_generation()
            logger.debug(f'Image generation is enabled, price: ${self.image_generation_price}, size: {self.image_generation_size}, style: {self.image_generation_style}, quality: {self.image_generation_quality}')

        self.function_calling = self.text_engine.function_calling
        if self.function_calling:
            self.load_function_calling(self.text_engine.name)
            self.text_engine.function_calling_tools = self.function_calling_tools
            logger.debug(f'Function calling is enabled')

        self.speech_engine = None
        try:
            if config.has_section("AudioTranscript"):
                self.speech_engine = get_audio_engine(config.get("AudioTranscript", "Engine"))
            elif config.has_section("OpenAI") and config.has_option("OpenAI", "WhisperModel"):
                logger.info("Deprecated call of OpenAI Whisper model")
                self.speech_engine = get_audio_engine("whisper")
            else:
                logger.info("No audio transcription engine provided")
                self.speech_engine = None
        except Exception as e:
            logger.error(f"Failed to initialize audio engine: {e}")
            raise Exception(f"Failed to initialize audio engine: {e}")
        
        self.system_message = self.text_engine.system_message 
        print('System message:', self.system_message)
        print('-- System message is used to set personality to the bot. It can be changed in the self.config file.')
        if self.summarize_too_long:
            print('-- Summarize too long is set to True. It means that if the text is too long, then it will be summarized instead of trimmed.\n')

        self.file_summary_tokens = config.getint("Files", "MaxSummaryTokens", fallback = (self.max_tokens // 2))
        self.max_file_length = config.getint("Files", "MaxFileLength", fallback = 10000)

        # load chat history from file
        self.chats_location = "./data/tech/chats.pickle"
        self.chats = self.load_pickle(self.chats_location)
        # load statistics from file
        self.stats_location = "./data/tech/stats.pickle"
        self.stats = self.load_pickle(self.stats_location)

        if self.log_chats:
            logger.info('* Chat history is logged *')

    def load_function_calling(self, textengine):
        '''
        Load function calling tools
        '''
        if textengine == "OpenAI":
            from chatutils.tools_config import OpenAIConfig
            tools_config = OpenAIConfig()
        if textengine == "Anthropic":
            from chatutils.tools_config import AnthropicConfig 
            tools_config = AnthropicConfig()
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
                    self.url_summary = config.getboolean("Web", "URLSummary", fallback=False)
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
                elif config.get("ImageGeneration", "Engine").lower() in ["yandex", "yandexart"]:
                    # Yandex Art
                    from chatutils.image_engines import YandexEngine
                    self.image_generation_engine_name = "yandex"
                    if config.has_option("ImageGeneration", "APIKey"):
                        api_key = config.get("ImageGeneration", "APIKey")
                    else:
                        logger.error("No API key provided for image generation")
                        raise Exception("No API key provided for image generation")
                    self.image_engine = YandexEngine(api_key)
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

    async def speech_to_text(self, file_path):
        try:
            if self.speech_engine is None:
                return None
            
            logger.debug(f"TranscribeOnly setting in speech_to_text: {self.speech_engine.settings['TranscribeOnly']}")
            transcript = await self.speech_engine.transcribe(file_path)
            return transcript
        except Exception as e:
            logger.exception('Could not convert speech to text')
            return None

    async def process_audio_video(self, id=0, file_path=None):
        try:
            if self.speech_engine is None:
                logger.error('No speech2text engine provided')
                return er.speech_to_text_na

            audio = AudioSegment.from_file(file_path)
            audio_duration = len(audio) / 1000.0  # Duration in seconds

            transcript = await self.speech_to_text(file_path)
            if transcript is None:
                logger.error('Could not convert audio/video to text')
                return er.speech_to_text_error

            # Add statistics
            await self.add_stats(id=id, speech2text_seconds=audio_duration)

            logger.debug(f"TranscribeOnly setting: {self.speech_engine.settings['TranscribeOnly']}")

            if self.speech_engine.settings["TranscribeOnly"]:
                logger.debug("Returning transcription only due to TranscribeOnly setting")
                return f"Transcription: {transcript}"

            logger.info("Processing transcription through chat")
            response = await self.chat(id=id, message=transcript)
            # Return response only, it is more natural
            return response
        except Exception as e:
            logger.exception('Could not process audio/video')
            return None

    async def chat_voice(self, id=0, audio_file=None):
        '''
        Chat with GPT using voice
        Input id of user and audio file
        '''
        try:
            if self.speech_engine is None:
                logger.error('No speech2text engine provided')
                return er.speech_to_text_na
            # convert voice to text
            if audio_file is not None:
                transcript = await self.speech_to_text(audio_file)
            else:
                logger.error('No audio file provided for voice chat')
                return None
            if transcript is None:
                logger.error('Could not convert voice to text')
                return er.speech_to_text_error
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
            if id not in self.chats:
                # If there is no chat, then create it
                success = await self.init_style(id=id)
                if not success:
                    logger.error('Could not init style for user: ' + str(id))
                    return False

            messages = self.chats[id]
            
            new_message = Message()
            new_message.role = "user"
            new_message.content_type = "image"
            new_message.content = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_b64}"
                }
            }
            messages.append(new_message)

            # Add flag that there is an image without caption
            self.pending_images[id] = True
            # save chat history
            self.chats[id] = messages
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
            messages[-1].content.append({
                "type": "text",
                "text": caption,
            })
            # save chat history
            self.chats[id] = messages
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
                style += '\n# You have vision capabilities enabled'
            # if function calling is enabled, then add information about it
            if self.function_calling:
                style += '\n# You have function calling (tools) enabled'
            # get messages if chat exists
            if id in self.chats:
                messages = self.chats[id]
            else:
                new_message = Message()
                new_message.role = "system"
                new_message.content = style
                messages = [new_message]
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open(self.chats_location, "wb"))
            return True
        except Exception as e:
            logger.error(f'Could not init style for user `{id}` due to an error: {e}')
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
        Trim messages (leave only last trim_count messages and system message)
        '''
        try:
            if messages is None or len(messages) <= 1:
                logger.debug('Could not trim messages due to a short conversation')
                return None
            if messages[0].role == 'system':
                system_message = messages[0]
                messages = messages[1:]
            else:
                system_message = Message()
                system_message.role = "system"
                system_message.content = self.system_message

            logger.debug(f'Trimming {len(messages)} messages, leaving only {trim_count} last messages')
            messages = messages[-trim_count:]
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
                logger.info('Could not summarize messages due to a short conversation')
                return messages
            if messages[0].role == 'system':
                system_message = messages[0]
                messages = messages[1:]
            else:
                system_message = Message()
                system_message.role = "system"
                system_message.content = self.system_message
            
            logger.debug(f'Summarizing {len(messages)} messages')
            last_messages = messages[-leave_messages:]

            summary = await self.chat_summary(messages)

            messages = []
            messages.append(system_message)
            messages.append(summary)

            for message in last_messages:
                messages.append(message)

            logger.debug(f'Summarized messages to {len(messages)} messages')
            return messages
        except Exception as e:
            logger.error(f'Could not summarize messages: {e}')
            return None
        
    async def process_function_calling(self, function):
        '''
        Process function calling
        Input FunctionResponse
        '''
        try:
            if function is None:
                logger.error('No function provided for processing')
                return None
            if function.function_name == 'generate_image':
                # call function to generate image
                function_to_call = self.available_functions[function.function_name]
                function_response = await function_to_call(
                    prompt = function.function_args.get("prompt"),
                    image_orientation = function.function_args.get("image_orientation"),
                    image_style = function.function_args.get("image_style"),
                )
                image, text = function_response[0], function_response[1]
                if image is not None:
                    # add statistics
                    logger.debug('Image was generated')
                    await self.add_stats(id=id, images_generated=1)
                    function.image = image
                    function.text = text
                    response = function
                elif image is None and text is not None:
                    response = f'Image was not generated. {text}'
                    logger.error(f'Function was called, but image was not generated: {response}')
                else:
                    response = er.general_error
            elif function.function_name == 'web_search':
                # call function to search the web
                function_to_call = self.available_functions[function.function_name]
                function_response = await function_to_call(
                    query = function.function_args.get("query"),
                )
                if function_response is None:
                    function_response = 'Error while searching the web'
                response = function_response
            elif function.function_name == 'url_opener':
                # call function to open URL
                function_to_call = self.available_functions[function.function_name]
                function_response = await function_to_call(
                    url = function.function_args.get("url"),
                )
                if function_response is None:
                    function_response = 'Error while opening the URL or there was no content'
                elif self.url_summary:
                    # create summary of the content
                    logger.debug(f'Attempting to summarize the content of the URL ({len(function_response)})')
                    function_response, token_usage = await self.text_engine.summary(f'URL content: {function_response}')
                    if function_response is None:
                        function_response = 'Error while summarizing the content of the URL'
                    else:
                        await self.add_stats(id=id, prompt_tokens_used=int(token_usage['prompt']), completion_tokens_used=int(token_usage['completion']))
                else:
                    pass
                response = function_response
            return response
        except Exception as e:
            logger.exception('Could not process function calling')
            return None

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
                    return er.style_initiation
            # get messages
            messages = self.chats[id]
            # If there is an image without caption, then add caption
            if self.vision and id in self.pending_images:
                self.chats[id] = messages
                await self.add_caption(id, message)
                messages = self.chats[id]
            else:
                # Add message to the chat
                new_message = Message()
                new_message.role = "user"
                new_message.content = message
                await self.add_to_chat_history(id=id, message=new_message)

            # Trim and summarize messages if conversation is too long
            if len(messages)-1 > self.trim_size:
                if self.trim_too_long:
                    messages = await self.trim_messages(messages)
                if self.summarize_too_long:
                    messages = await self.summarize_messages(messages)

            # Wait for response
            response_message = await self.text_engine.chat(id=id, messages=messages)
            if response_message is None:
                return er.message_answer_error
            if response_message.error is not None:
                return er.get_error_for_message(response_message.error)

            if self.function_calling and response_message.content_type == 'function':
                # process function calling
                function_response = await self.process_function_calling(response_message.content)
                if function_response is None:
                    return er.function_calling_error
                else:
                    return function_response
            await self.add_stats(id=id, prompt_tokens_used=prompt_tokens, completion_tokens_used=completion_tokens)
            response = response_message.content
            return response
        except Exception as e:
            logger.exception('Could not get answer to message: ' + message + ' from user: ' + str(id))
            return er.message_answer_error
        
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
                    new_message = Message()
                    new_message.role = "assistant"
                    new_message.content = f"<system - image was generated from the prompt: {prompt}>"
                    await self.add_to_chat_history(id=id, message=new_message)
                # add text to chat if it is not None
                if revision:
                    text = 'Revised prompt: ' + text
                else:
                    text = None
            if image is None and text is None:
                return None, er.image_generation_error
            # return image
            return image, text
        except Exception as e:
            logger.error(f'Could not generate image from prompt `{prompt}` for user: {id}')
            return None, er.image_generation_error
            
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
                return er.general_error
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
