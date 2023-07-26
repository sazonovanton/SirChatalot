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
import tiktoken
import os
from pydub import AudioSegment
import hashlib
from datetime import datetime

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
            self.end_user_id = config.getboolean("OpenAI", "EndUserID") if config.has_option("OpenAI", "EndUserID") else False
            self.log_chats = config.getboolean("OpenAI", "LogChats") if config.has_option("OpenAI", "LogChats") else False
            try:
                self.system_message = config.get("OpenAI", "SystemMessage")
            except Exception as e:
                self.system_message = "You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages."
                logger.exception('Could not get system message from config, using default: ' + self.system_message)
            print('System message:', self.system_message)
            print('-- System message is used to set personality to the bot. It can be changed in the config file.\n')

            self.file_summary_tokens = int(config.get("OpenAI", "MaxSummaryTokens")) if config.has_option("OpenAI", "MaxSummaryTokens") else (self.max_tokens // 2)
            self.max_file_length = int(config.get("OpenAI", "MaxFileLength")) if config.has_option("OpenAI", "MaxFileLength") else 10000

            self.min_length_tokens = int(config.get("OpenAI", "MinLengthTokens")) if config.has_option("OpenAI", "MinLengthTokens") else 100
            # load chat history from file if exists or create new 
            try:
                self.chats = pickle.load(open("./data/tech/chats.pickle", "rb")) 
            except:
                self.chats = {}

            # load statistics by users from file if exists or create new 
            try:
                self.stats = pickle.load(open("./data/tech/stats.pickle", "rb")) 
            except:
                self.stats = {}

            self.max_chat_length = int(config.get("OpenAI", "MaxSessionLength")) if config.has_option("OpenAI", "MaxSessionLength") else None
            self.chat_deletion = config.getboolean("OpenAI", "ChatDeletion") if config.has_option("OpenAI", "ChatDeletion") else False
            if self.max_chat_length is not None:
                print('Max chat length:', self.max_chat_length)
                print('-- Max chat length is states a length of chat session. It can be changed in the config file.\n')
            if self.chat_deletion:
                print('Chat deletion is enabled')
                print('-- Chat deletion is used to force delete old chat sessions. Without it long sessions should be summaried. It can be changed in the config file.\n')

            self.moderation = config.getboolean("OpenAI", "Moderation") if config.has_option("OpenAI", "Moderation") else False
            if self.moderation:
                print('Moderation is enabled')
                print('-- Moderation is used to check if content complies with OpenAI usage policies. It can be changed in the config file.')
                print('-- Learn more: https://platform.openai.com/docs/guides/moderation/overview\n')

        except Exception as e:
            logger.exception('Could not initialize GPT class')

    def count_tokens(self, messages):
        '''
        Count tokens in messages via tiktoken
        '''
        try:
            encoding = tiktoken.encoding_for_model(self.model)
            tokens = 0
            for message in messages:
                text = message['role'] + ': ' + message['content']
                tokens += len(encoding.encode(text))
            return tokens
        except Exception as e:
            logger.exception('Could not count tokens in text')
            return None

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
            if id is not None and id in self.stats:
                statisitics = ''
                for key, value in self.stats[id].items():
                    statisitics += key + ': ' + str(value) + '\n'
                cost = self.stats[id]['Tokens used'] / 1000 * self.model_price if self.model_prompt_price == 0 and self.model_completion_price == 0 else 0
                cost += self.stats[id]['Speech2text seconds'] / 60 * self.s2t_model_price
                cost += self.stats[id]['Prompt tokens used'] / 1000 * self.model_prompt_price 
                cost += self.stats[id]['Completion tokens used'] / 1000 * self.model_completion_price
                statisitics += '\nAppoximate cost of usage is $' + str(round(cost, 4)) + ' 😊'
                return statisitics
            return None
        except Exception as e:
            logger.exception('Could not get statistics for user: ' + str(id))
            return None

    def dump_chat(self, id=0, plain=False) -> bool:
        '''
        Dump chat to a file
        If plain is True, then dump chat as plain text with roles and messages
        If plain is False, then dump chat as pickle file
        '''
        try:
            # get chat history
            try:
                messages = self.chats[id]
            except:
                return False
            # dump chat to a file with filename: ./data/chats/123456_20230721-182531.pickle
            if plain:
                with open(f'./data/chats/{id}_{datetime.now().strftime("%Y%m%d-%H%M%S")}.txt', 'w') as f:
                    for message in messages:
                        f.write(message['role'] + ': ' + message['content'] + '\n')
            else:
                pickle.dump(messages, open(f"./data/chats/{id}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.pickle", "wb"))
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
            if self.log_chats:
                self.dump_chat(id=id, plain=True)
            del self.chats[id]
            pickle.dump(self.chats, open("./data/tech/chats.pickle", "wb"))
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
        
    def stored_sessions(self, id=0):
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

    def load_session(self, id=0, name=None):
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
            pickle.dump(self.chats, open("./data/tech/chats.pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not load session for user: ' + str(id))
            return False

    def delete_session(self, id=0, name=None):
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
            logger.info('Deleted session named: ' + str(name) + ', for user: ' + str(id))
            return True
        except Exception as e:
            logger.exception('Could not delete session for user: ' + str(id))
            return False
        
    
    def speech_to_text(self, audio_file):
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
            audio_file = str(audio_file)
            os.remove(audio_file.replace('.ogg', self.audio_format))
            logger.info('Audio file ' + audio_file.replace('.ogg', self.audio_format) + ' was deleted (converted)')
        except Exception as e:
            logger.exception('Could not delete converted audio file: ' + str(audio_file))
        return transcript

    def convert_ogg_to_wav(self, audio_file):
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

    def chat_voice(self, id=0, audio_file=None):
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

    def summary(self, text, size=240):
        '''
        Make summary of text
        Input text and size of summary (in tokens)
        '''
        summary = [{"role": "system", "content": f'You are very great at summarizing text to fit in {size//30} sentenses. Answer with summary only.'}]
        summary.append({"role": "user", "content": 'Make a summary:\n' + str(text)})
        user_id = hashlib.sha1(str(id).encode("utf-8")).hexdigest() if self.end_user_id else None
        requested_tokens = min(size, self.max_tokens)
        response = openai.ChatCompletion.create(
                model=self.model,
                temperature=self.temperature, 
                max_tokens=requested_tokens,
                messages=summary,
                user=user_id
        )
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
            for i in range(1, len(messages)):
                text += messages[i]['role'] + ': ' + messages[i]['content'] + '\n'
            if short:
                summary = self.summary(text, size=30)
            else:
                summary = self.summary(text)
            return summary
        except Exception as e:
            logger.exception('Could not summarize chat history')
            return None

    def moderation_pass(self, message, id=0):
        '''
        Moderate message with GPT
        Input message and id of user
        '''
        try:
            # check if message is not empty
            if message is None or len(message) == 0:
                return None

            # check if ./data/moderation.txt exists and create if not
            if not os.path.exists('./data/moderation.txt'):
                open('./data/moderation.txt', 'a').close()
            
            response = openai.Moderation.create(
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

    def filechat(self, id=0, text='', sumdepth=3):
        '''
        Process file with GPT
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
                        text += self.summary(chunk, size=self.file_summary_tokens) + '\n'
                text = '# Summary from recieved file: #\n' + text
            else:
                # if text is shorter than self.max_tokens // 2, then do not make summary
                text = '# Text from recieved file: #\n' + text
            # chat with GPT
            response = self.chat(id=id, message=text)
            return response
        except Exception as e:
            logger.exception('Could not chat with GPT')
            return None

    def chat(self, id=0, message="Hi! Who are you?", style=None, continue_attempt=True):
        '''
        Chat with GPT
        Input id of user and message
        '''
        try:
            self.delete_chat_after_response = False 
            # get chat history
            try:
                messages = self.chats[id]
            except:
                if style is None:
                    style = self.system_message
                messages = [{"role": "system", "content": style}]
            # send messsage to moderation if moderation is enabled
            if self.moderation:
                if self.moderation_pass(message, id) == False:
                    return 'Your message was flagged as violating OpenAI\'s usage policy and was not sent. Please try again.'
            # add new message
            messages.append({"role": "user", "content": message})
            # check length of chat 
            if self.max_chat_length is not None:
                l = len([i for i in messages if i['role'] == 'user'])
                if self.max_chat_length > 0:
                    if l > self.max_chat_length-1:
                        if self.chat_deletion == True:
                            self.delete_chat_after_response = True 
                        else:
                            style = messages[0]['content'] + '\n Your previous conversation summary: '
                            self.delete_chat(id)
                            style += self.chat_summary(messages)
                            self.chat(id=id, message=message, style=style, continue_attempt=False)
                    
            # get response from GPT
            try:
                user_id = hashlib.sha1(str(id).encode("utf-8")).hexdigest() if self.end_user_id else None
                requested_tokens = min(self.max_tokens, self.max_tokens - self.count_tokens(messages))
                response = openai.ChatCompletion.create(
                        model=self.model,
                        temperature=self.temperature, 
                        max_tokens=requested_tokens,
                        messages=messages,
                        user=user_id
                )
            # if ratelimit is reached
            except openai.error.RateLimitError as e:
                logger.exception('Rate limit error')
                return 'Service is getting rate limited. Please try again later.'
            # if chat is too long
            except openai.error.InvalidRequestError as e:
                # if 'openai.error.InvalidRequestError: The model: `gpt-4` does not exist'
                if 'does not exist' in str(e):
                    logger.error(f'Invalid model error for model {self.model}')
                    return 'Something went wrong with an attempt to use the model. Please contact the developer.'
                logger.exception('Invalid request error')
                if self.chat_deletion is not None:
                    print(messages)
                    print(e)
                    self.delete_chat(id)
                    return 'We had to reset your chat session due to an error. Please try again.'
                else:
                    if not continue_attempt:
                        return 'We had to reset your chat session due to an error. Please try to delete the chat manually with /delete command and try again.'
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
            if self.delete_chat_after_response == True:
                self.delete_chat(id)
                response += '\n\n***System***\nSorry. Your session is longer than max session length limit, so we reset it after this message.'
                self.delete_chat_after_response = False
                return response
            # add response to chat history
            messages.append({"role": "assistant", "content": response})
            # save chat history
            self.chats[id] = messages
            # save chat history to file
            # it would be more efficient to save the chat history periodically, such as every few minutes, but it's ok for now
            pickle.dump(self.chats, open("./data/tech/chats.pickle", "wb"))
            if self.max_chat_length is not None and self.chat_deletion == True:
                l = len([i for i in messages if i['role'] == 'user'])
                if self.max_chat_length - l <= 3:
                    response += '\n\n***System***\nYou are close to the session limit. Messages left: ' + str(self.max_chat_length - l) + '.'
            if continue_attempt == False:
                # if chat is too long, return response and advice to delete session
                response += '\nIt seems like you reached length limit of chat session. You can continue, but I advice you to /delete session.'
            return response
        except Exception as e:
            logger.exception('Could not get answer to message: ' + message + ' from user: ' + str(id))
            return None

    def keyword_trigger(self, message):
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
        


if __name__ == "__main__":
    # test GPT class
    gpt = GPT()
    # gpt.chat(id=0, message="Hi! Who are you?")
    print(gpt.stats)
