# Description: Chats processing class

import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-Engines")
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler('./logs/common.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import os
import hashlib
import tiktoken

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
            "LogChats": False,
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
        self.log_chats = self.config.getboolean("OpenAI", "LogChats") 

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
                self.delete_chat(id)
                return 'We had to reset your chat session due to an error. Please try again.', messages[:-1], {"prompt": prompt_tokens, "completion": completion_tokens}  
            else:
                logger.info(f'Chat session for user {id} was summarized due to an error')
                style = messages[0]['content'] + '\n Your previous conversation summary: '
                self.delete_chat(id)
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