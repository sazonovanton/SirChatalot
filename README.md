# SirChatalot

This is a Telegram bot that uses the OpenAI [ChatGPT API](https://beta.openai.com/docs/api-reference/chat) to generate responses to messages. I just wanted to test the OpenAI ChatGPT API and I thought that a Telegram bot would be a good way to do it. Some things can be unnecessary complicated. 

This bot can also be used to generate responses to voice messages. Bot will convert the voice message to text and will then generate a response. Speech recognition is done using the OpenAI [Whisper model](https://platform.openai.com/docs/guides/speech-to-text). To use this feature, you need to install the [ffmpeg](https://ffmpeg.org/) library.

## Getting Started
* Clone the repository.
* Create a bot using the [BotFather](https://t.me/botfather).
* Install the required packages by running the command pip install -r requirements.txt.
* Install the [ffmpeg](https://ffmpeg.org/) library (converts .ogg files to .wav files) for voice message support.
* Create a .config file in the data directory using the config.example file as a template.
* Run the bot by running the command `python3 main.py`.

Whitelist.txt, .config and chats.pickle are stored in the `./data` directory. Logs rotate every day and are stored in the `./logs` directory.

Bot is designed to talk to you in a style of a knight in the middle ages. You can change that in the `gptproc.py` file.

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
* OpenAI.Model: The model to use for generating responses (ChatGPT is powered by `gpt-3.5-turbo` for now).
* OpenAI.Temperature: The temperature to use for generating responses.
* OpenAI.MaxTokens: The maximum number of tokens to use for generating responses.

## Running the Bot
To run the bot, simply run the command `python3 main.py`. The bot will start and will wait for messages. 
The bot has the following commands:
* `/start`: starts the conversation with the bot.
* `/help`: shows the help message.
* `/delete`: deletes the conversation history.
* Any other message (including voice message) will generate a response from the bot.

Users need to be whitelisted to use the bot. To whitelist yourself, send an access code to the bot using the /start command. The bot will then add you to the whitelist and will send a message to you confirming that you have been added to the whitelist.

## Adding Users to the Whitelist
To add users to the whitelist, send the bot a message with one of the access codes (see *Configuration*). The bot will then add the user to the whitelist and will send a message to the user confirming that they have been added to the whitelist.

## Generating Responses
To generate a response, send the bot a message (or a voice message). The bot will then generate a response and send it back to you.

## Warinings
* The bot stores the whitelist in plain text. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot stores chat history in as a pickle file. The file is not encrypted and can be accessed by anyone with access to the server.
* Configurations are stored in plain text. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot can store messages in a log file in a event of an error. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot temporarily stores voice messages in `./data/voice` directory. The files are deleted after processing, but can remain on the server if the event of an error. The files are not encrypted and can be accessed by anyone with access to the server.
* The bot is not designed to be used in production environments. It is not secure and was build as a proof of concept and for ChatGPT API testing purposes.
* Use this bot at your own risk. I am not responsible for any damage caused by this bot.

## License
This project is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) license. See the LICENSE file for more details.

## Acknowledgements
* [OpenAI ChatGPT API](https://beta.openai.com/docs/api-reference/chat)
* [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text)
* [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
* [FFmpeg](https://ffmpeg.org/)
