# SirChatalot

This is a Telegram bot that uses the OpenAI [ChatGPT API](https://beta.openai.com/docs/api-reference/chat) to generate responses to messages. I just wanted to test the OpenAI ChatGPT API and I thought that a Telegram bot would be a good way to do it.

## Getting Started
* Clone the repository.
* Install the required packages by running the command pip install -r requirements.txt.
* Create a .config file in the data directory using the config.example file as a template.
* Run the bot by running the command `python3 main.py`.

Whitelist.txt, .config and chats.pickle are stored in the `./data` directory. Logs rotate every day and are stored in the `./logs` directory.

## Configuration
The bot requires a configuration file to run. The configuration file should be in [INI file format](https://en.wikipedia.org/wiki/INI_file) and should contain the following fields:
```
[Telegram]
Token = 0000000000:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AccessCodes = whitelistcode,secondwhitelistcode

[OpenAI]
SecretKey = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Model = gpt-3.5-turbo
Temperature = 0.7
MaxTokens = 500
```
* Telegram.Token: The token for the Telegram bot.
* Telegram.AccessCodes: A comma-separated list of access codes that can be used to add users to the whitelist.
* OpenAI.SecretKey: The secret key for the OpenAI API.
* OpenAI.Model: The model to use for generating responses (see [here](https://beta.openai.com/docs/api-reference/models) for a list of models).
* OpenAI.Temperature: The temperature to use for generating responses.
* OpenAI.MaxTokens: The maximum number of tokens to use for generating responses.

## Running the Bot
To run the bot, simply run the command `python3 main.py`. The bot will start and will wait for messages. 
The bot has the following commands:
* `/start`: starts the conversation with the bot.
* `/help`: shows the help message.
* `/delete`: deletes the conversation history.
Any other message will generate a response from the bot.

Users need to be whitelisted to use the bot. To whitelist yourself, send an access code to the bot using the /start command. The bot will then add you to the whitelist and will send a message to you confirming that you have been added to the whitelist.

## Adding Users to the Whitelist
To add users to the whitelist, send the bot a message with one of the access codes (see *Configuration*). The bot will then add the user to the whitelist and will send a message to the user confirming that they have been added to the whitelist.

## Generating Responses
To generate a response, send the bot a message. The bot will then generate a response and send it back to you.

## Warinings
* The bot stores the whitelist in plain text. The file is not encrypted and should not be shared with anyone.
* The bot stores chat history in as a pickle file. The file is not encrypted and should not be shared with anyone.
* Configurations are stored in plain text. The file is not encrypted and should not be shared with anyone.
* The bot can store messages in a log file in a event of an error. The file is not encrypted and should not be shared with anyone.
* The bot is not designed to be used in production environments. It is not secure and was build as a proof of concept and for ChatGPT API testing purposes.

## License
This project is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) license. See the LICENSE file for more details.

## Acknowledgements
* [OpenAI ChatGPT API](https://beta.openai.com/docs/api-reference/chat)
* [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
