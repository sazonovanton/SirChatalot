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

class GPT:
    def __init__(self) -> None:
        '''
        Initialize GPT class
        '''
        try:
            openai.api_key = config.get("OpenAI", "SecretKey")
            self.model = config.get("OpenAI", "Model")
            self.temperature = float(config.get("OpenAI", "Temperature"))
            self.max_tokens = int(config.get("OpenAI", "MaxTokens"))

            # load chat history from file if exists or create new 
            try:
                # using pickle to load dict from file is not a safe way, but it's ok for this example
                # pickle can be manipulated to execute arbitrary code
                self.chats = pickle.load(open("./data/chats.pickle", "rb")) 
            except:
                self.chats = {}
        except Exception as e:
            logger.exception('Could not initialize GPT class')

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
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
            audio_file.close()
            transcript = transcript['text']
            return transcript
        except Exception as e:
            logger.exception('Could not convert voice to text')
            return None

    def convert_ogg_to_wav(self, audio_file) -> str:
        '''
        Convert ogg file to wav
        Input file with ogg
        '''
        try:
            # convert ogg to wav
            wav_file = audio_file.replace('.ogg', '.wav')
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
                    try:
                        os.remove(audio_file.replace('.ogg', '.wav'))
                        logger.info('Wav audio file ' + audio_file.replace('.ogg', '.wav') + ' was deleted')
                    except Exception as e:
                        logger.exception('Could not delete audio file: ' + audio_file)
            else:
                logger.error('No audio file provided for voice chat')
                return None
            # get chat history
            try:
                messages = self.chats[id]
            except:
                messages = [{"role": "system", "content": "You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages."}]
            # add new message
            messages.append({"role": "user", "content": transcript})
            # get response from GPT
            response = openai.ChatCompletion.create(
                model=self.model,
                temperature=self.temperature, 
                max_tokens=self.max_tokens,
                messages=messages
            )
            response = response["choices"][0]['message']['content']
            # add response to chat history
            messages.append({"role": "assistant", "content": response})
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            # this can be unsafe, but it's ok for this example
            pickle.dump(self.chats, open("./data/chats.pickle", "wb"))
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
                messages = [{"role": "system", "content": "You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages."}]
            # add new message
            messages.append({"role": "user", "content": message})
            # get response from GPT
            response = openai.ChatCompletion.create(
                model=self.model,
                temperature=self.temperature, 
                max_tokens=self.max_tokens,
                messages=messages
            )
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
    print(gpt.chat())
    print(gpt.delete_chat())
