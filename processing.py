# Description: Chats processing class

import configparser
config = configparser.ConfigParser()
config.read('./data/.config')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-Processing")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/common.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import pickle
import os
from pydub import AudioSegment
from datetime import datetime

# Support: OpenAI API, YandexGPT API
# Planned: Text Generation WebUI API, Runpod API 
from engines import OpenAIEngine, YandexEngine

class ChatProc:
    def __init__(self, text="OpenAI", speech="OpenAI") -> None:
        text = text.lower()
        speech = speech.lower() if speech is not None else None
        self.max_tokens = 2000
        self.log_chats = config.getboolean("Logging", "LogChats") if config.has_option("Logging", "LogChats") else False
        self.model_prompt_price, self.model_completion_price = 0, 0
        self.audio_format, self.s2t_model_price = ".wav", 0
        if text == "openai":
            self.text_engine = OpenAIEngine(text=True)
            self.max_tokens = self.text_engine.max_tokens
            self.model_prompt_price = self.text_engine.model_prompt_price
            self.model_completion_price = self.text_engine.model_completion_price
        elif text == "yagpt" or text == "yandexgpt" or text == "yandex":
            self.text_engine = YandexEngine(text=True)
        # elif text == "textgen" or text == "text-generation-webui":
        #     self.text_engine = TextgenEngine(text=True)
        # elif text == "runpod":
        #     self.text_engine = RunpodEngine(text=True)
        else:
            logger.error("Unknown text engine: {}".format(text))
            raise Exception("Unknown text engine: {}".format(text))
        
        if speech is None:
            self.speech_engine = None
        elif speech == "openai":
            self.speech_engine = OpenAIEngine(speech=True)
            self.audio_format = self.speech_engine.audio_format
            self.s2t_model_price = self.speech_engine.s2t_model_price
        # elif speech == "runpod":
        #     self.speech_engine = RunpodEngine(speech=True)
        else:
            logger.error("Unknown speech2text engine: {}".format(speech))
            raise Exception("Unknown speech2text engine: {}".format(speech))
        
        self.system_message = self.text_engine.system_message 
        print('System message:', self.system_message)
        print('-- System message is used to set personality to the bot. It can be changed in the self.config file.\n')

        self.file_summary_tokens = int(config.get("Files", "MaxSummaryTokens")) if config.has_option("OpenAI", "MaxSummaryTokens") else (self.max_tokens // 2)
        self.max_file_length = int(config.get("Files", "MaxFileLength")) if config.has_option("OpenAI", "MaxFileLength") else 10000

        # load chat history from file
        self.chats = self.load_pickle("./data/tech/chats.pickle")
        # load statistics from file
        self.stats = self.load_pickle("./data/tech/stats.pickle")

    def speech_to_text(self, audio_file):
        '''
        Convert speech to text
        Input file with speech
        '''
        if self.speech_engine is None:
            return None
        try:
            transcript = self.speech_engine.speech_to_text(audio_file)
            transcript += ' (it was a voice message transcription)'
        except Exception as e:
            logger.exception('Could not convert voice to text')
            transcript = None
        if transcript is not None:
            # add statistics
            try:
                audio = AudioSegment.from_wav(audio_file.replace('.ogg', self.audio_format))
                self.add_stats(id=id, speech2text_seconds=audio.duration_seconds)
            except Exception as e:
                logger.exception('Could not add speech2text statistics for user: ' + str(id))
        # delete audio file
        try:
            audio_file = str(audio_file)
            os.remove(audio_file.replace('.ogg', self.audio_format))
            logger.debug('Audio file ' + audio_file.replace('.ogg', self.audio_format) + ' was deleted (converted)')
        except Exception as e:
            logger.exception('Could not delete converted audio file: ' + str(audio_file))
        return transcript
    
    def chat_voice(self, id=0, audio_file=None):
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
                transcript = self.speech_to_text(audio_file)
            else:
                logger.error('No audio file provided for voice chat')
                return None
            if transcript is None:
                logger.error('Could not convert voice to text')
                return 'Sorry, I could not convert your voice to text.'
            response = self.chat(id=id, message=transcript)
            return response
        except Exception as e:
            logger.exception('Could not voice chat with GPT')
            return None
    
    def chat(self, id=0, message="Hi! Who are you?", style=None):
        '''
        Chat with GPT
        Input id of user and message
        '''
        try:
            try:
                if id not in self.chats:
                    if style is None:
                        style = self.system_message
                    messages = [{"role": "system", "content": style}]
                else:
                    messages = self.chats[id]
            except Exception as e:
                logger.exception('Could not get chat history for user: ' + str(id))
                messages = [{"role": "system", "content": self.system_message}]
            messages.append({"role": "user", "content": message})
            # * response - response (just text of last reply)
            #       "I am fine, how are you?"
            # * messages - messages (all messages - list of dictionaries with last message at the end)
            #       [{"role": "system", "content": "You are a helpful assistant named Sir Chat-a-lot."},
            #       {"role": "user", "content": "Hello, how are you?"},
            #       {"role": "assistant", "content": "I am fine, how are you?"},...]
            # * tokens_used - number of tokens used in response
            #       {"prompt": int, "completion": int}
            response, messages, tokens_used = self.text_engine.chat(id=id, messages=messages)
            # add statistics
            try:
                self.add_stats(id=id, completion_tokens_used=int(tokens_used['completion']))
                self.add_stats(id=id, prompt_tokens_used=int(tokens_used['prompt']))
            except Exception as e:
                logger.exception('Could not add tokens used in statistics for user: ' + str(id) + ' and response: ' + str(response))
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open("./data/tech/chats.pickle", "wb"))
            return response
        except Exception as e:
            logger.exception('Could not get answer to message: ' + message + ' from user: ' + str(id))
            return 'Sorry, I could not get an answer to your message. Please try again or contact the administrator.'
    
    def load_pickle(self, filepath):
        '''
        Load pickle file if exists or create new 
        '''
        try:
            payload = pickle.load(open(filepath, "rb")) 
            return payload
        except:
            payload = {}
            pickle.dump(payload, open(filepath, "wb"))
            return payload
        
    def add_stats(self, id=None, speech2text_seconds=None, messages_sent=None, voice_messages_sent=None, prompt_tokens_used=None, completion_tokens_used=None) -> None:
        '''
        Add statistics (tokens used, messages sent, voice messages sent) by user
        Input id of user, tokens used, speech2text in seconds used, messages sent, voice messages sent
        '''
        try:
            if id is None:
                logger.debug('Could not add stats. No ID provided')
                return None
            if id not in self.stats:
                self.stats[id] = {'Tokens used': 0, 'Speech2text seconds': 0, 'Messages sent': 0, 'Voice messages sent': 0, 'Prompt tokens used': 0, 'Completion tokens used': 0}
            self.stats[id]['Speech2text seconds'] += round(speech2text_seconds) if speech2text_seconds is not None else 0
            self.stats[id]['Messages sent'] += messages_sent if messages_sent is not None else 0
            self.stats[id]['Voice messages sent'] += voice_messages_sent if voice_messages_sent is not None else 0
            self.stats[id]['Prompt tokens used'] += prompt_tokens_used if prompt_tokens_used is not None else 0
            self.stats[id]['Completion tokens used'] += completion_tokens_used if completion_tokens_used is not None else 0
            # save statistics to file (unsafe way)
            pickle.dump(self.stats, open("./data/tech/stats.pickle", "wb"))
        except Exception as e:
            logger.exception('Could not add statistics for user: ' + str(id))

    def get_stats(self, id=None):
        '''
        Get statistics (tokens used, speech2text in seconds used, messages sent, voice messages sent) by user
        Input id of user
        '''
        try:
            # get statistics by user
            if id is None:
                logger.debug('Get statistics - ID was not provided')
                return None
            if id in self.stats:
                statisitics = ''
                for key, value in self.stats[id].items():
                    if key in ['Tokens used']:
                        continue # deprecated values
                    statisitics += key + ': ' + str(value) + '\n'
                cost = self.stats[id]['Speech2text seconds'] / 60 * self.s2t_model_price
                cost += self.stats[id]['Prompt tokens used'] / 1000 * self.model_prompt_price 
                cost += self.stats[id]['Completion tokens used'] / 1000 * self.model_completion_price
                statisitics += '\nAppoximate cost of usage is $' + str(round(cost, 4))
                return statisitics
            return None
        except Exception as e:
            logger.exception('Could not get statistics for user: ' + str(id))
            return None
        
    def dump_chat(self, id=None, plain=False, chatname=None) -> bool:
        '''
        Dump chat to a file
        If plain is True, then dump chat as plain text with roles and messages
        If plain is False, then dump chat as pickle file
        '''
        try:
            if id is None:
                logger.debug('Could not dump chat. No ID provided')
                return False
            if id not in self.chats:
                return False
            if name is None:
                name = datetime.now().strftime("%Y%m%d-%H%M%S")
            messages = self.chats[id]
            if plain:
                # dump chat to a file with filename: ./data/chats/123456_20230721-182531.txt
                with open(f'./data/chats/{id}_{chatname}.txt', 'w') as f:
                    for message in messages:
                        f.write(message['role'] + ': ' + message['content'] + '\n')
            else:
                # dump chat to user file with filename: ./data/chats/123456.pickle
                filename = f'./data/chats/{id}.pickle'
                chats = self.load_pickle(filename)
                chats[chatname] = messages
                pickle.dump(chats, open(filename, "wb"))
            return True
        except Exception as e:
            logger.exception('Could not dump chat for user: ' + str(id))
            return False
        
    def delete_chat(self, id=0) -> bool:
        '''
        Delete chat history
        Input id of user
        '''
        try:
            if id not in self.chats:
                return False
            if self.log_chats:
                self.dump_chat(id=id, plain=True)
            del self.chats[id]
            pickle.dump(self.chats, open("./data/tech/chats.pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not delete chat history for user: ' + str(id))
            return False

    def stored_sessions(self, id=None):
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
        
    def load_session(self, id=None, chatname=None):
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
            pickle.dump(self.chats, open("./data/tech/chats.pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not load session for user: ' + str(id))
            return False

    def delete_session(self, id=0, chatname=None):
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
        
    def change_style(self, id=0, style=None):
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
            messages[0]['content'] = style
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            pickle.dump(self.chats, open("./data/tech/chats.pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not change style for user: ' + str(id))
            return False

    def filechat(self, id=0, text='', sumdepth=3):
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
                        text += self.text_engine.summary(chunk, size=self.file_summary_tokens) + '\n'
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


