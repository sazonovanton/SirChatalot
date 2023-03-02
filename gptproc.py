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

class GPT:
    def __init__(self, model_capability='full') -> None:
        '''
        Initialize GPT class
        '''
        openai.api_key = config.get("OpenAI", "SecretKey")
        self.model = config.get("OpenAI", "Model")
        self.temperature = float(config.get("OpenAI", "Temperature"))
        self.max_tokens = int(config.get("OpenAI", "MaxTokens"))

        # load chat history from file if exists or create new 
        try:
            self.chats = pickle.load(open("./data/chats.pickle", "rb"))
        except:
            self.chats = {}

    def delete_chat(self, id=0) -> bool:
        '''
        Delete chat history
        '''
        try:
            del self.chats[id]
            pickle.dump(self.chats, open("./data/chats.pickle", "wb"))
            return True
        except Exception as e:
            logger.exception('Could not delete chat history for user: ' + str(id))
            return False

    def chat(self, id=0, message="Hi! Who are you?") -> str:
        '''
        Chat with GPT
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
