# Description: Chats processing class

import configparser
config = configparser.ConfigParser()
config.read('./data/.config')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-Engines")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/common.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import os
import hashlib
import tiktoken

######## OpenAI Engine ########

class OpenAIEngine:
    def __init__(self, text=False, speech=False):
        '''
        Initialize OpenAI API 
        Available: text generation, speech2text
        '''
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
            })
        self.config.read('./data/.config')   
        self.openai.api_key = self.config.get("OpenAI", "SecretKey")  

        self.text_initiation, self.speech_initiation = text, speech
        self.text_init() if self.text_initiation else None
        self.speech_init() if self.speech_initiation else None

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

    def speech_init(self):
        '''
        Initialize speech2text
        '''  
        self.s2t_model = self.config.get("OpenAI", "WhisperModel")
        self.s2t_model_price = float(self.config.get("OpenAI", "WhisperModelPrice")) 
        self.audio_format = '.' + self.config.get("OpenAI", "AudioFormat") 

    def convert_ogg(self, audio_file):
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
        
    def speech_to_text(self, audio_file):
        '''
        Convert speech to text using OpenAI API
        '''
        if self.speech_initiation == False:
            return None
        audio_file = self.convert_ogg(audio_file)
        audio = open(audio_file, "rb")
        transcript = self.openai.Audio.transcribe(self.s2t_model, audio)
        audio.close()
        transcript = transcript['text']
        return transcript
    
    def chat(self, id=0, messages=None, attempt=0):
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
        '''
        if self.text_initiation == False:
            return None, None, None
        if messages is None:
            return None, None, None
        # send last message to moderation
        message = messages[-1]['content']
        prompt_tokens, completion_tokens = 0, 0
        if self.moderation:
            if self.moderation_pass(message, id) == False:
                return 'Your message was flagged as violating OpenAI\'s usage policy and was not sent. Please try again.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}    
        # get response from GPT
        try:
            user_id = hashlib.sha1(str(id).encode("utf-8")).hexdigest() if self.end_user_id else None
            requested_tokens = min(self.max_tokens, self.max_tokens - self.count_tokens(messages))
            requested_tokens = max(requested_tokens, 50)
            response = self.openai.ChatCompletion.create(
                    model=self.model,
                    temperature=self.temperature, 
                    max_tokens=requested_tokens,
                    messages=messages,
                    user=user_id
            )
            prompt_tokens = int(response["usage"]['prompt_tokens'])
            completion_tokens = int(response["usage"]['completion_tokens'])
        # if ratelimit is reached
        except self.openai.error.RateLimitError as e:
            logger.exception('Rate limit error')
            return 'Service is getting rate limited. Please try again later.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # if chat is too long
        except self.openai.error.InvalidRequestError as e:
            # if 'openai.error.InvalidRequestError: The model: `gpt-4` does not exist'
            if 'does not exist' in str(e):
                logger.error(f'Invalid model error for model {self.model}')
                return 'Something went wrong with an attempt to use the model. Please contact the developer.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens} 
            logger.exception('Invalid request error')
            if self.chat_deletion or attempt > 0:
                logger.info(f'Chat session for user {id} was deleted due to an error')
                messages = messages[0]
                return 'We had to reset your chat session due to an error. Please try again.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}  
            else:
                logger.info(f'Chat session for user {id} was summarized due to an error')
                style = messages[0]['content'] + '\n Your previous conversation summary: '
                style += self.chat_summary(messages[:-1])
                response, messages, token_usage = self.chat(id=id, messages=[{"role": "system", "content": style}, {"role": "user", "content": message}], attempt=attempt+1)
                prompt_tokens += int(token_usage['prompt'])
                completion_tokens += int(token_usage['completion'])
        # if something else
        except Exception as e:
            logger.exception('Could not get response from GPT')
            return None, messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}
        # process response
        response = response["choices"][0]['message']['content']
        # add response to chat history
        messages.append({"role": "assistant", "content": response})
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

    def summary(self, text, size=240):
        '''
        Make summary of text
        Input text and size of summary (in tokens)
        '''
        # Get a summary prompt
        summary = [{"role": "system", "content": f'You are very great at summarizing text to fit in {size//30} sentenses. Answer with summary only.'}]
        summary.append({"role": "user", "content": 'Make a summary:\n' + str(text)})
        # Get the response from the API
        requested_tokens = min(size, self.max_tokens)
        response = self.openai.ChatCompletion.create(
                model=self.model,
                temperature=self.temperature, 
                max_tokens=requested_tokens,
                messages=summary
        )
        # Return the response
        return response["choices"][0]['message']['content']

    def chat_summary(self, messages, short=False):
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
                text += messages[i]['role'] + ': ' + messages[i]['content'] + '\n'
            if short:
                # Generate short summary
                summary = self.summary(text, size=30)
            else:
                # Generate long summary
                summary = self.summary(text)
            return summary
        except Exception as e:
            logger.exception('Could not summarize chat history')
            return None

    def moderation_pass(self, message, id=0):
        try:
            # check if message is not empty
            if message is None or len(message) == 0:
                return None
            # check if ./data/moderation.txt exists and create if not
            if not os.path.exists('./data/moderation.txt'):
                open('./data/moderation.txt', 'a').close()
            response = self.openai.Moderation.create(
                input=message
            )
            output = response["results"][0]
            if output["flagged"] == "true" or output["flagged"] == True:
                categories = output["categories"]
                # get flagged categories
                flagged_categories = [k for k, v in categories.items() if v == "true" or v == True]
                # log used id, flagged message and flagged categories to ./data/moderation.txt
                with open('./data/moderation.txt', 'a') as f:
                    f.write(str(id) + '\t' + str(flagged_categories) + '\t' + message + '\n')
                # log to logger file fact of user being flagged
                logger.info('Message from user ' + str(id) + ' was flagged (' + str(flagged_categories) + ')')
                return False
            return True
        except Exception as e:
            logger.exception('Could not moderate message')
            return None

    def count_tokens(self, messages):
        '''
        Count tokens in messages via tiktoken
        '''
        try:
            # Get the encoding for the model
            encoding = tiktoken.encoding_for_model(self.model)
            # Count the number of tokens
            tokens = 0
            for message in messages:
                text = message['role'] + ': ' + message['content']
                tokens += len(encoding.encode(text))
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
        


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
            })
        self.config.read('./data/.config') 
        self.chat_vars = {} 
        self.chat_vars['KeyID'] = self.config.get("YandexGPT", "KeyID")  
        self.chat_vars['SecretKey'] = self.config.get("YandexGPT", "SecretKey")   
        self.chat_vars['CatalogID'] = self.config.get("YandexGPT", "CatalogID")
        self.chat_vars['Endpoint'] = self.config.get("YandexGPT", "ChatEndpoint")
        self.chat_vars['InstructEndpoint'] = self.config.get("YandexGPT", "InstructEndpoint")
        self.chat_vars['Model'] = self.config.get("YandexGPT", "ChatModel")
        self.chat_vars['PartialResults'] = self.config.getboolean("YandexGPT", "PartialResults")
        self.chat_vars['Temperature'] = self.config.getfloat("YandexGPT", "Temperature")
        self.chat_vars['MaxTokens'] = self.config.getint("YandexGPT", "MaxTokens")
        self.chat_vars['instructionText'] = self.config.get("YandexGPT", "instructionText")
        self.log_chats = self.config.getboolean("Logging", "LogChats") if self.config.has_option("Logging", "LogChats") else False
        self.system_message = self.chat_vars['instructionText']
        self.max_tokens = self.chat_vars['MaxTokens']
        self.model_prompt_price = 0
        self.model_completion_price = 0

    def speech_init(self):
        '''
        Initialize Yandex API for speech synthesis
        '''
        # TODO: implement speech to text with Yandex API
        pass

    def chat(self, messages, id=0, attempt=0):
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
            tokens = self.count_tokens(messages)
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
                "messages": self.format_messages(messages),
                "instructionText": self.chat_vars['instructionText']
            }
            logger.debug(f'Payload to Yandex API: {payload}')
            response = self.requests.post(self.chat_vars['Endpoint'], json=payload, headers=headers)
            logger.debug(f'Response from Yandex API. Code: {response.status_code}, text: {response.text}')
            # check if response is successful
            if response.status_code != 200:
                if response.status_code == 429 and attempt == 0:
                    # TODO: figure out correct error if messages length is too long
                    attempt += 1
                else:
                    logger.error(f'Could not send message to Yandex API, response status code: {response.status_code}, response: {response.json()}')
                    user_message = 'Sorry, something went wrong. Please try to /delete and /start again.'
                    return user_message, messages, None
            if attempt == 1:
                logger.warning(f'Session is too long for user {id}, summarrizing and sending last message')
                # summary messages
                style = messages[0]['content'] + '\n Your previous conversation summary: '
                style += self.chat_summary(messages[:-1])
                response, messages, token_usage = self.chat(id=id, messages=[{"role": "system", "content": style}, {"role": "user", "content": message}], attempt=attempt+1)
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

    def format_messages(self, messages):
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
        
    def summary(self, text, size=240):
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
    
    def chat_summary(self, messages, short=False):
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
                text += messages[i]['role'] + ': ' + messages[i]['content'] + '\n'
            if short:
                # Generate short summary
                summary = self.summary(text, size=30)
            else:
                # Generate long summary
                summary = self.summary(text)
            return summary
        except Exception as e:
            logger.exception('Could not summarize chat history')
            return None
    
    def count_tokens(self, messages, model='gpt-3.5-turbo'):
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
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
        

######## Text Generation WebUI Engine ########

class TextGenEngine:
    def __init__(self, text=False, speech=False):
        '''
        Initialize Text Generation WebUI API Engine
        '''
        self.text = text
        self.speech = speech
        import requests
        import json
        self.requests = requests
        self.json = json

        self.text_initiation = text
        self.text_init() if self.text_initiation else None
        
        if self.speech:
            logger.warning('Speech to Text is not supported in Text Generation WebUI Engine')

    def text_init(self):
        '''
        Initialize Text Generation WebUI API Engine
        '''
        import configparser
        self.config = configparser.SafeConfigParser({
            "Host": "127.0.0.1:5000",
            "SSL": False,
            "max_new_tokens": 250,
            "mode": "chat",
            "character": "Sir Chatalot",
            "instruction_template": '',
            "user_name": 'User',
            "prompt": "Your name is Sir Chatalot. You are helpful AI assistaint.",
            "chat-instruct_command": 'Continue the chat dialogue below. Write a single reply for the character "<|character|>".\n<|prompt|>',
            'preset': '',
            'do_sample': True,
            'temperature': 0.7,
            'top_p': 0.1,
            'typical_p': 1,
            'epsilon_cutoff': 0,  
            'eta_cutoff': 0,  
            'tfs': 1,
            'top_a': 0,
            'repetition_penalty': 1.18,
            'repetition_penalty_range': 0,
            'top_k': 40,
            'min_length': 0,
            'no_repeat_ngram_size': 0,
            'num_beams': 1,
            'penalty_alpha': 0,
            'length_penalty': 1,
            'early_stopping': False,
            'mirostat_mode': 0,
            'mirostat_tau': 5,
            'mirostat_eta': 0.1,

            'seed': -1,
            'add_bos_token': True,
            'truncation_length': 2048,
            'ban_eos_token': False,
            'skip_special_tokens': True,
            'stopping_strings': []
            })
        self.config.read('./data/.config') 
        self.chat_vars = {} 
        self.chat_vars['Host'] = self.config.get('TextGenWebUI', 'Host')
        self.chat_vars['SSL'] = self.config.getboolean('TextGenWebUI', 'SSL')
        self.chat_vars['URI'] = 'https://' if self.chat_vars['SSL'] else 'http://' + self.chat_vars['Host'] + '/api/v1/chat'
        self.chat_vars['max_new_tokens'] = self.config.getint('TextGenWebUI', 'max_new_tokens')
        self.chat_vars['mode'] = self.config.get('TextGenWebUI', 'mode')
        self.chat_vars['character'] = self.config.get('TextGenWebUI', 'character')
        self.chat_vars['user_name'] = self.config.get('TextGenWebUI', 'user_name')
        self.chat_vars['instruction_template'] = self.config.get('TextGenWebUI', 'instruction_template')
        self.chat_vars['instruction_template'] = None if self.chat_vars['instruction_template'] == '' else self.chat_vars['instruction_template']
        self.chat_vars['chat-instruct_command'] = self.config.get('TextGenWebUI', 'chat-instruct_command')
        self.chat_vars['prompt'] = self.config.get('TextGenWebUI', 'prompt')
        self.chat_vars['preset'] = self.config.get('TextGenWebUI', 'preset')
        self.chat_vars['preset'] = None if self.chat_vars['preset'] == '' else self.chat_vars['preset']
        self.chat_vars['do_sample'] = self.config.getboolean('TextGenWebUI', 'do_sample')
        self.chat_vars['temperature'] = self.config.getfloat('TextGenWebUI', 'temperature')
        self.chat_vars['top_p'] = self.config.getfloat('TextGenWebUI', 'top_p')
        self.chat_vars['typical_p'] = self.config.getfloat('TextGenWebUI', 'typical_p')
        self.chat_vars['epsilon_cutoff'] = self.config.getfloat('TextGenWebUI', 'epsilon_cutoff')
        self.chat_vars['eta_cutoff'] = self.config.getfloat('TextGenWebUI', 'eta_cutoff')
        self.chat_vars['tfs'] = self.config.getfloat('TextGenWebUI', 'tfs')
        self.chat_vars['top_a'] = self.config.getfloat('TextGenWebUI', 'top_a')
        self.chat_vars['repetition_penalty'] = self.config.getfloat('TextGenWebUI', 'repetition_penalty')
        self.chat_vars['repetition_penalty_range'] = self.config.getfloat('TextGenWebUI', 'repetition_penalty_range')
        self.chat_vars['top_k'] = self.config.getint('TextGenWebUI', 'top_k')
        self.chat_vars['min_length'] = self.config.getint('TextGenWebUI', 'min_length')
        self.chat_vars['no_repeat_ngram_size'] = self.config.getint('TextGenWebUI', 'no_repeat_ngram_size')
        self.chat_vars['num_beams'] = self.config.getint('TextGenWebUI', 'num_beams')
        self.chat_vars['penalty_alpha'] = self.config.getfloat('TextGenWebUI', 'penalty_alpha')
        self.chat_vars['length_penalty'] = self.config.getfloat('TextGenWebUI', 'length_penalty')
        self.chat_vars['early_stopping'] = self.config.getboolean('TextGenWebUI', 'early_stopping')
        self.chat_vars['mirostat_mode'] = self.config.getint('TextGenWebUI', 'mirostat_mode')
        self.chat_vars['mirostat_tau'] = self.config.getfloat('TextGenWebUI', 'mirostat_tau')
        self.chat_vars['mirostat_eta'] = self.config.getfloat('TextGenWebUI', 'mirostat_eta')
        self.chat_vars['seed'] = self.config.getint('TextGenWebUI', 'seed')
        self.chat_vars['add_bos_token'] = self.config.getboolean('TextGenWebUI', 'add_bos_token')
        self.chat_vars['truncation_length'] = self.config.getint('TextGenWebUI', 'truncation_length')
        self.chat_vars['ban_eos_token'] = self.config.getboolean('TextGenWebUI', 'ban_eos_token')
        self.chat_vars['skip_special_tokens'] = self.config.getboolean('TextGenWebUI', 'skip_special_tokens')
        self.chat_vars['stopping_strings'] = self.config.get('TextGenWebUI', 'stopping_strings').split(',')
        self.log_chats = self.config.getboolean("Logging", "LogChats") if self.config.has_option("Logging", "LogChats") else False
        self.system_message = self.chat_vars['chat-instruct_command']
        self.max_tokens = self.chat_vars['max_new_tokens']
        self.model_prompt_price = 0
        self.model_completion_price = 0
        
    def count_tokens(self, messages, model='gpt-3.5-turbo'):
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
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None
        
    def format_messages(self, messages):
        '''
        Format messages for Text Generation WebUI API
        From: [
            {"role": "user", "content": "Hi there"}
            {"role": "assistaint", "content": "Hello, I am an AI. How can i help you?"}
            ...]
        To: {
                internal: [ ["Hi there","Hello, I am an AI. How can i help you?"], ["Please explain how language models work",""] ],
                visible: [ ["Hi there","Hello, I am an AI. How can i help you?"], ["Please explain how language models work",""] ]
            }
        Also delete message with role "system"
        '''
        try:
            internal = []
            visible = []
            # message group:
            message_group = {'user': '', 'assistant': ''}
            user_input = messages[-1]['content'] if messages[-1]['role'] == 'user' else ''
            messages = messages[:-1]
            for message in messages:
                if message['role'] == 'system':
                    continue
                elif message['role'] == 'user':
                    message_group['user'] = message['content']
                elif message['role'] == 'assistant':
                    message_group['assistant'] = message['content']
                    internal.append([message_group['user'], message_group['assistant']])
                    visible.append([message_group['user'], message_group['assistant']])
                    message_group = {'user': '', 'assistant': ''}
            if message_group['user'] != '' or message_group['assistant'] != '':
                internal.append([message_group['user'], message_group['assistant']])
                visible.append([message_group['user'], message_group['assistant']])
            history = {'internal': internal, 'visible': visible}
            return user_input, history
        except Exception as e:
            logger.exception('Could not format messages for Text Generation WebUI API')
            raise Exception('Could not format messages for Text Generation WebUI API')

    def chat(self, messages, id=0, attempt=0):
        '''
        Chat with Text Generation WebUI API
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
            prompt_tokens = 0
            tokens = self.chat_vars['max_new_tokens']
            # # count tokens in messages
            # tokens = self.count_tokens(messages)
            # if tokens is not None:
            #     tokens = self.chat_vars['max_new_tokens'] - tokens
            #     tokens = max(tokens, 30)
            # else:
            #     tokens = self.chat_vars['max_new_tokens'] // 2
            # format messages
            user_input, history = self.format_messages(messages)
            user_name = None
            # format request
            request = {
                'user_input': user_input,
                'max_new_tokens': tokens,
                'history': history,
                'mode': self.chat_vars['mode'],
                'character': self.chat_vars['character'],
                'instruction_template': self.chat_vars['instruction_template'],
                # 'context_instruct': '',  # Optional
                'your_name': user_name,
                # 'regenerate': False,
                # '_continue': False,
                # 'stop_at_newline': False,
                # 'chat_generation_attempts': 1,
                'chat-instruct_command': self.chat_vars['chat-instruct_command'],
                'do_sample': self.chat_vars['do_sample'],
                'temperature': self.chat_vars['temperature'],
                'top_p': self.chat_vars['top_p'],
                'typical_p': self.chat_vars['typical_p'],
                'epsilon_cutoff': self.chat_vars['epsilon_cutoff'],
                'eta_cutoff': self.chat_vars['eta_cutoff'],
                'tfs': self.chat_vars['tfs'],
                'top_a': self.chat_vars['top_a'],
                'repetition_penalty': self.chat_vars['repetition_penalty'],
                'repetition_penalty_range': self.chat_vars['repetition_penalty_range'],
                'top_k': self.chat_vars['top_k'],
                'min_length': self.chat_vars['min_length'],
                'no_repeat_ngram_size': self.chat_vars['no_repeat_ngram_size'],
                'num_beams': self.chat_vars['num_beams'],
                'penalty_alpha': self.chat_vars['penalty_alpha'],
                'length_penalty': self.chat_vars['length_penalty'],
                'early_stopping': self.chat_vars['early_stopping'],
                'mirostat_mode': self.chat_vars['mirostat_mode'],
                'mirostat_tau': self.chat_vars['mirostat_tau'],
                'mirostat_eta': self.chat_vars['mirostat_eta'],
                'seed': self.chat_vars['seed'],
                'add_bos_token': self.chat_vars['add_bos_token'],
                'truncation_length': self.chat_vars['truncation_length'],
                'ban_eos_token': self.chat_vars['ban_eos_token'],
                'skip_special_tokens': self.chat_vars['skip_special_tokens'],
                'stopping_strings': self.chat_vars['stopping_strings'],
            }
            # send request
            response = self.requests.post(self.chat_vars['URI'], json=request)
            if response.status_code == 200:
                result = response.json()['results'][0]['history']
                # print(self.json.dumps(result, indent=4))
                response = result['visible'][-1][1]
                messages = messages.append({'role': 'assistant', 'content': response})
            else:
                logger.warning('Could not get response from Text Generation WebUI API')
                response = 'Something went wrong. Please try again later.'
            return response, messages, {'prompt': prompt_tokens, 'completion': completion_tokens}
        except Exception as e:
            logger.exception('Could not chat with Text Generation WebUI API')
            return None, messages, {'prompt': 0, 'completion': 0}




####### TEST #######
if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)

    # engine = OpenAIEngine(text=True)
    engine = YandexEngine(text=True)
    # engine = TextGenEngine(text=True)
    messages = [
        {"role": "system", "content": "Your name is Sir Chatalot, you are assisting the user with a task."},
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I am fine, how are you?"},
        {"role": "user", "content": "I am fine too. Please tell me what is the weather like today?"},
    ]
    print('\n***        Test        ***')
    response, messages, tokens = engine.chat(messages=messages, id=0)
    print('============================')
    print(response)
    print('------------------')
    for message in messages:
        print(message['role'], ':', message['content'])
    print('----------------------------')
    print(tokens)
    print('============================')