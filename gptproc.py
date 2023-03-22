# Description: ChatGPT processing class

import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-GPT")
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler('./logs/common.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

# import configuration 
import configparser
config = configparser.ConfigParser()
config.read('./data/.config')

import pickle
import openai
import os
from pydub import AudioSegment

class GPT:
    def __init__(self) -> None:
        '''
        Initialize GPT class
        '''
        try:
            openai.api_key = config.get("OpenAI", "SecretKey")
            self.model = config.get("OpenAI", "ChatModel")
            self.model_price = float(config.get("OpenAI", "ChatModelPrice")) if config.has_option("OpenAI", "ChatModelPrice") else 0 # per 1000 tokens
            self.model_completion_price = float(config.get("OpenAI", "ChatModelCompletionPrice")) if config.has_option("OpenAI", "ChatModelCompletionPrice") else 0 # per 1000 tokens
            self.model_prompt_price = float(config.get("OpenAI", "ChatModelPromptPrice")) if config.has_option("OpenAI", "ChatModelPromptPrice") else 0 # per 1000 tokens
            self.s2t_model = config.get("OpenAI", "WhisperModel")
            self.s2t_model_price = float(config.get("OpenAI", "WhisperModelPrice")) if config.has_option("OpenAI", "WhisperModelPrice") else 0 # per 1000 tokens
            self.temperature = float(config.get("OpenAI", "Temperature"))
            self.max_tokens = int(config.get("OpenAI", "MaxTokens"))
            self.audio_format = '.' + config.get("OpenAI", "AudioFormat") # wav or mp3
            try:
                self.system_message = config.get("OpenAI", "SystemMessage")
            except Exception as e:
                self.system_message = "You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages."
                logger.exception('Could not get system message from config, using default: ' + self.system_message)
            print('System message:', self.system_message)
            print('-- System message is used to set personality to the bot. It can be changed in the config file.\n')

            # load chat history from file if exists or create new 
            try:
                # using pickle is not a safe way, but it's ok for this example
                # pickle can be manipulated to execute arbitrary code
                self.chats = pickle.load(open("./data/chats.pickle", "rb")) 
            except:
                self.chats = {}

            # load statistics by users from file if exists or create new
            try:
                # using pickle is not a safe way, but it's ok for this example
                # pickle can be manipulated to execute arbitrary code
                self.stats = pickle.load(open("./data/stats.pickle", "rb")) 
            except:
                self.stats = {}

            self.max_chat_length = int(config.get("OpenAI", "MaxSessionLength"))*2 if config.has_option("OpenAI", "MaxSessionLength") else None

        except Exception as e:
            logger.exception('Could not initialize GPT class')

    def add_stats(self, id=None, tokens_used=None, speech2text_seconds=None, messages_sent=None, voice_messages_sent=None, prompt_tokens_used=None, completion_tokens_used=None) -> None:
        '''
        Add statistics (tokens used, messages sent, voice messages sent) by user
        Input id of user, tokens used, speech2text in seconds used, messages sent, voice messages sent
        '''
        try:
            # add statistics by user
            if id is not None:
                if id not in self.stats:
                    self.stats[id] = {'Tokens used': 0, 'Speech2text seconds': 0, 'Messages sent': 0, 'Voice messages sent': 0, 'Prompt tokens used': 0, 'Completion tokens used': 0}
                if tokens_used is not None:
                    try:
                        self.stats[id]['Tokens used'] += tokens_used
                    except:
                        self.stats[id]['Tokens used'] = tokens_used
                if speech2text_seconds is not None:
                    try:
                        self.stats[id]['Speech2text seconds'] += round(speech2text_seconds)
                    except:
                        self.stats[id]['Speech2text seconds'] = round(speech2text_seconds)
                if messages_sent is not None:
                    try:
                        self.stats[id]['Messages sent'] += messages_sent
                    except:
                        self.stats[id]['Messages sent'] = messages_sent
                if voice_messages_sent is not None:
                    try:
                        self.stats[id]['Voice messages sent'] += voice_messages_sent
                    except:
                        self.stats[id]['Voice messages sent'] = voice_messages_sent
                if prompt_tokens_used is not None:
                    try:
                        self.stats[id]['Prompt tokens used'] += prompt_tokens_used
                    except:
                        self.stats[id]['Prompt tokens used'] = prompt_tokens_used
                if completion_tokens_used is not None:
                    try:
                        self.stats[id]['Completion tokens used'] += completion_tokens_used
                    except:
                        self.stats[id]['Completion tokens used'] = completion_tokens_used
            # save statistics to file (unsafe way)
            pickle.dump(self.stats, open("./data/stats.pickle", "wb"))
        except Exception as e:
            logger.exception('Could not add statistics for user: ' + str(id))

    def get_stats(self, id=None) -> str:
        '''
        Get statistics (tokens used, speech2text in seconds used, messages sent, voice messages sent) by user
        Input id of user
        '''
        try:
            # get statistics by user
            if id is not None and id in self.stats:
                statisitics = ''
                for key, value in self.stats[id].items():
                    statisitics += key + ': ' + str(value) + '\n'
                cost = self.stats[id]['Tokens used'] / 1000 * self.model_price if self.model_prompt_price == 0 and self.model_completion_price == 0 else 0
                cost += self.stats[id]['Speech2text seconds'] / 60 * self.s2t_model_price
                cost += self.stats[id]['Prompt tokens used'] / 1000 * self.model_prompt_price 
                cost += self.stats[id]['Completion tokens used'] / 1000 * self.model_completion_price
                statisitics += '\nAppoximate cost of usage is $' + str(round(cost, 4)) + '\nDo not worry, it is free for you 😊'
                return statisitics
            return None
        except Exception as e:
            logger.exception('Could not get statistics for user: ' + str(id))
            return None

    def delete_chat(self, id=0) -> bool:
        '''
        Delete chat history
        Input id of user
        '''
        try:
            del self.chats[id]
            pickle.dump(self.chats, open("./data/chats.pickle", "wb"))
            return True
        except Exception as e:
            # logger.exception('Could not delete chat history for user: ' + str(id))
            return False

    def save_session(self, id=0) -> bool:
        '''
        Save chat session 
        Input id of user
            file: ./data/chats/ID.pickle
            content of file: {'Name 1': messages, 'Name 2': messages, ...}
        '''
        # get chat history
        try:
            messages = self.chats[id]
        except:
            return False
        # read user sessions from pickle file if exists 

        try:
            sessions = pickle.load(open("./data/chats/" + str(id) + ".pickle", "rb"))
        except:
            sessions = {}
            logger.info('Could not load sessions for user: ' + str(id) + ', creating new')

        # get name of chat by summarizing messages
        summary = self.chat_summary(messages, short=True)

        # save chat session
        try:
            sessions[summary] = messages
            pickle.dump(sessions, open("./data/chats/" + str(id) + ".pickle", "wb"))
            logger.info('Saved session for user: ' + str(id) + ', name: ' + summary)
            return True
        except Exception as e:
            logger.exception('Could not save session for user: ' + str(id))
            return False
        
    def stored_sessions(self, id=0) -> list:
        '''
        Get list of stored sessions for user
        '''
        # read user sessions from pickle file if exists 
        try:
            sessions = pickle.load(open("./data/chats/" + str(id) + ".pickle", "rb"))
        except:
            return None
        
        # sessions names
        names = []
        for key, value in sessions.items():
            names.append(key)
            print('*', key)
        return names

    def load_session(self, id=0, name=None) -> list:
        '''
        Load chat session by name for user, overwrite chat history with session
        '''
        # read user sessions from pickle file if exists
        try:
            sessions = pickle.load(open("./data/chats/" + str(id) + ".pickle", "rb"))
        except:
            return False
        
        # get session by name
        try:
            messages = sessions[name]
            # overwrite chat history
            self.chats[id] = messages
            pickle.dump(self.chats, open("./data/chats.pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not load session for user: ' + str(id))
            return False

    def delete_session(self, id=0, name=None) -> bool:
        '''
        Delete chat session by name for user
        '''
        # read user sessions from pickle file if exists
        try:
            sessions = pickle.load(open("./data/chats/" + str(id) + ".pickle", "rb"))
        except:
            return False
        
        # delete session by name
        try:
            del sessions[name]
            pickle.dump(sessions, open("./data/chats/" + str(id) + ".pickle", "wb"))
            logger.info('Deleted session named: ' + name + ', for user: ' + str(id))
            return True
        except Exception as e:
            logger.exception('Could not delete session for user: ' + str(id))
            return False
        
    
    def speech_to_text(self, audio_file) -> str:
        '''
        Convert speech to text
        Input file with speech
        '''
        try:
            # convert voice to text
            audio_file = self.convert_ogg_to_wav(audio_file)
            audio = open(audio_file, "rb")
            transcript = openai.Audio.transcribe(self.s2t_model, audio)
            audio.close()
            transcript = transcript['text']
            transcript += ' (it was a voice message transcription)'
        except Exception as e:
            logger.exception('Could not convert voice to text')
            transcript = None

        # delete audio file
        try:
            os.remove(audio_file.replace('.ogg', self.audio_format))
            logger.info('Audio file ' + audio_file.replace('.ogg', self.audio_format) + ' was deleted (converted)')
        except Exception as e:
            logger.exception('Could not delete converted audio file: ' + audio_file)
        return transcript

    def convert_ogg_to_wav(self, audio_file) -> str:
        '''
        Convert ogg file to wav
        Input file with ogg
        '''
        try:
            # convert ogg to wav
            wav_file = audio_file.replace('.ogg', self.audio_format)
            os.system('ffmpeg -i ' + audio_file + ' ' + wav_file)
            return wav_file
        except Exception as e:
            logger.exception('Could not convert ogg to wav')
            return Noneself.add_stats

    def chat_voice(self, id=0, audio_file=None) -> str:
        '''
        Chat with GPT using voice
        Input id of user and audio file
        '''
        try:
            # convert voice to text
            if audio_file is not None:
                transcript = self.speech_to_text(audio_file)
                if transcript is not None:
                    # add statistics
                    try:
                        audio = AudioSegment.from_wav(audio_file.replace('.ogg', self.audio_format))
                        self.add_stats(id=id, speech2text_seconds=audio.duration_seconds)
                    except Exception as e:
                        logger.exception('Could not add speech2text statistics for user: ' + str(id))
            else:
                logger.error('No audio file provided for voice chat')
                return None
            # chat with GPT
            response = self.chat(id=id, message=transcript)
            return response
        except Exception as e:
            logger.exception('Could not voice chat with GPT')
            return None

    def chat_summary(self, messages, short=False) -> str:
        '''
        Summarize chat history
        Input messages and short flag (states that summary should be in one sentence)
        '''
        try:
            if messages is None or len(messages) == 0:
                return None

            text = ''
            for i in range(1, len(messages)):
                text += messages[i]['role'] + ': ' + messages[i]['content'] + '\n'
            if short:
                summary = [{"role": "system", "content": 'You are summarizing given text in an only one short sentence with a few words. Answer with summary only.'}]
                summary.append({"role": "user", "content": 'Make a summary: ' + str(text)})
                size = 12
            else:
                summary = [{"role": "system", "content": 'You are very great at summarizing text to fit at 500 charaters. Answer with summary only.'}]
                summary.append({"role": "user", "content": 'Make a summary of the previous conversation: ' + str(text)})
                size = self.max_tokens

            response = openai.ChatCompletion.create(
                model=self.model,
                temperature=self.temperature, 
                max_tokens=size,
                messages=summary
            )

            return response["choices"][0]['message']['content']
        except Exception as e:
            logger.exception('Could not summarize chat history')
            return None
        

    def chat(self, id=0, message="Hi! Who are you?", style=None, continue_attempt=True) -> str:
        '''
        Chat with GPT
        Input id of user and message
        '''
        # trigger_style = self.keyword_trigger(message)
        # if trigger_style != False:
        #     self.change_style(id=id, style=trigger_style)
        try:
            # get chat history
            try:
                messages = self.chats[id]
            except:
                if style is None:
                    style = self.system_message
                messages = [{"role": "system", "content": style}]
            # add new message
            messages.append({"role": "user", "content": message})
            # check length of chat 
            if self.max_chat_length is not None:
                if self.max_chat_length > 0:
                    if len(messages) > self.max_chat_length:
                        ## UNCOMMENT THIS TO FORCE CHAT RESET
                        # self.delete_chat(id)
                        # return 'It seems that your session is too long. We have reset it. Please try again.'
                        style = messages[0]['content'] + '\n Your previous conversation summary: '
                        self.delete_chat(id)
                        style += self.chat_summary(messages)
                        self.chat(id=id, message=message, style=style, continue_attempt=False)
                    
            # get response from GPT
            try:
                response = openai.ChatCompletion.create(
                    model=self.model,
                    temperature=self.temperature, 
                    max_tokens=self.max_tokens,
                    messages=messages
                )
            # if ratelimit is reached
            except openai.error.RateLimitError as e:
                logger.exception('Rate limit error')
                return 'Wow... Service is getting rate limited. Please try again later.'
            # if chat is too long
            except openai.error.InvalidRequestError as e:
                logger.exception('Invalid request error')
                ## UNCOMMENT THIS TO FORCE CHAT RESET
                # self.delete_chat(id)
                # return 'It seems that your session is too long. We have reset it. Please try again.'
                if not continue_attempt:
                    return 'It seems that something in this chat session is wrong. Please try to start a new one with /delete'
                else:
                    style = messages[0]['content'] + '\n Your previous conversation summary: '
                    self.delete_chat(id)
                    style += self.chat_summary(messages)
                    self.chat(id=id, message=message, style=style, continue_attempt=False)
            # if something else
            except Exception as e:
                logger.exception('Could not get response from GPT')
                return None
            # add statistics
            try:
                self.add_stats(id=id, tokens_used=int(response["usage"]['total_tokens']))
                self.add_stats(id=id, completion_tokens_used=int(response["usage"]['completion_tokens']))
                self.add_stats(id=id, prompt_tokens_used=int(response["usage"]['prompt_tokens']))
            except Exception as e:
                logger.exception('Could not add tokens used in statistics for user: ' + str(id) + ' and response: ' + str(response))
            # process response
            response = response["choices"][0]['message']['content']
            # add response to chat history
            messages.append({"role": "assistant", "content": response})
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            # this can be expensive operation
            # it would be more efficient to save the chat history periodically, such as every few minutes, but it's ok for now
            pickle.dump(self.chats, open("./data/chats.pickle", "wb"))
            if continue_attempt == False:
                # if chat is too long, return response and advice to delete session
                response += '\nIt seems like you reached length limit of chat session. You can continue, but I advice you to /delete session.'
            return response
        except Exception as e:
            logger.exception('Could not get answer to message: ' + message + ' from user: ' + str(id))
            return None

    def keyword_trigger(self, message) -> bool:
        '''
        Search for keyword in message
        Input message and keyword
        '''
        styles = {
            'rose': 'You like roses, you talk about roses, you are a rose.',
            'sunflower': 'You like sunflowers, you talk about sunflowers, you are a sunflower.',
        }

        try:
            for keyword in styles:
                if keyword in message:
                    style = styles[keyword]
                    return style
                else:
                    return False
        except Exception as e:
            logger.exception('Could not search for keyword: ' + keyword + ' in message: ' + message)
            return False

    def change_style(self, id=0, style=None) -> bool:
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
            pickle.dump(self.chats, open("./data/chats.pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not change style for user: ' + str(id))
            return False
        


if __name__ == "__main__":
    # test GPT class
    gpt = GPT()
    # gpt.chat(id=0, message="Hi! Who are you?")
    print(gpt.stats)
