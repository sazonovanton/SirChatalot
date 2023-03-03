# Description: ChatGPT processing class

import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-GPT")
handler = TimedRotatingFileHandler('./logs/common.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setLevel(logging.INFO)
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
            self.model_price = float(config.get("OpenAI", "ChatModelPrice")) # per 1000 tokens
            self.s2t_model = config.get("OpenAI", "WhisperModel")
            self.s2t_model_price = float(config.get("OpenAI", "WhisperModelPrice")) # per minute
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

        except Exception as e:
            logger.exception('Could not initialize GPT class')

    def add_stats(self, id=None, tokens_used=None, speech2text_seconds=None, messages_sent=None, voice_messages_sent=None) -> None:
        '''
        Add statistics (tokens used, messages sent, voice messages sent) by user
        Input id of user, tokens used, speech2text in seconds used, messages sent, voice messages sent
        '''
        try:
            # add statistics by user
            if id is not None:
                if id not in self.stats:
                    self.stats[id] = {'Tokens used': 0, 'Speech2text seconds': 0, 'Messages sent': 0, 'Voice messages sent': 0}
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
                cost = self.stats[id]['Tokens used'] / 1000 * self.model_price + self.stats[id]['Speech2text seconds'] / 60 * self.s2t_model_price
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
            logger.exception('Could not delete chat history for user: ' + str(id))
            return False
    
    def speech_to_text(self, audio_file) -> str:
        '''
        Convert speech to text
        Input file with speech
        '''
        try:
            # convert voice to text
            audio_file = self.convert_ogg_to_wav(audio_file)
            audio_file = open(audio_file, "rb")
            transcript = openai.Audio.transcribe(self.s2t_model, audio_file)
            audio_file.close()
            transcript = transcript['text']
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
            return None

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

    def chat(self, id=0, message="Hi! Who are you?") -> str:
        '''
        Chat with GPT
        Input id of user and message
        '''
        try:
            # get chat history
            try:
                messages = self.chats[id]
            except:
                messages = [{"role": "system", "content": self.system_message}]
            # add new message
            messages.append({"role": "user", "content": message})
            # get response from GPT
            response = openai.ChatCompletion.create(
                model=self.model,
                temperature=self.temperature, 
                max_tokens=self.max_tokens,
                messages=messages
            )
            # add statistics
            try:
                self.add_stats(id=id, tokens_used=int(response["usage"]['total_tokens']))
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
            return response
        except Exception as e:
            logger.exception('Could not get answer to message: ' + message + ' from user: ' + str(id))
            return None


if __name__ == "__main__":
    # test GPT class
    gpt = GPT()
    # gpt.chat(id=0, message="Hi! Who are you?")
    print(gpt.stats)
