# SirChatalot

This is a Telegram bot that uses the OpenAI [ChatGPT API](https://platform.openai.com/docs/guides/chat) to generate responses to messages. I just wanted to test the API and I thought that a Telegram bot would be a good way to do it. Some things can be unnecessary complicated. 

This bot can also be used to generate responses to voice messages. Bot will convert the voice message to text and will then generate a response. Speech recognition is done using the OpenAI [Whisper model](https://platform.openai.com/docs/guides/speech-to-text). To use this feature, you need to install the [ffmpeg](https://ffmpeg.org/) library. Voice message support won't work without it.

## Getting Started
* Create a bot using the [BotFather](https://t.me/botfather).
* Clone the repository.
* Install the required packages by running the command `pip install -r requirements.txt`.
* Install the [ffmpeg](https://ffmpeg.org/) library for voice message support (for converting .ogg files to other format) and test it calling `ffmpeg -version` in the terminal. Voice message support won't work without it.
* Create a `.config` file in the `data` directory using the `config.example` file in that directory as a template.
* Run the bot by running the command `python3 main.py`.

Whitelist.txt, banlist.txt, .config, stats.pickle and chats.pickle are stored in the `./data` directory. Logs rotate every day and are stored in the `./logs` directory.

Bot is designed to talk to you in a style of a knight in the middle ages by default. You can change that in the `./data/.config` file (SystemMessage).
There are also some additional styles that you can choose from: Alice, Bob and Charlie. You can change style from chat by sending a message with `/style` command, but your current session will be dropped. 
Styles can be set up in the `main.py` file (`modes` variable). Style is kept only for a current session (until command `/delete` or `/style` will be issued). 

## Configuration
The bot requires a configuration file to run. The configuration file should be in [INI file format](https://en.wikipedia.org/wiki/INI_file) and should contain the following fields:
```
[Telegram]
Token = 0000000000:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AccessCodes = whitelistcode,secondwhitelistcode

[OpenAI]
SecretKey = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ChatModel = gpt-3.5-turbo
ChatModelPrice = 0.002
WhisperModel = whisper-1
WhisperModelPrice = 0.006
Temperature = 0.7
MaxTokens = 500
AudioFormat = wav
SystemMessage = You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages.
```
* Telegram.Token: The token for the Telegram bot.
* Telegram.AccessCodes: A comma-separated list of access codes that can be used to add users to the whitelist. If no access codes are provided, anyone who not in the banlist will be able to use the bot.
* OpenAI.SecretKey: The secret key for the OpenAI API.
* OpenAI.ChatModel: The model to use for generating responses (Chat can be powered by `gpt-3.5-turbo` for now).
* OpenAI.ChatModelPrice: The [price of the model](https://openai.com/pricing) to use for generating responses (per 1000 tokens, in USD).
* OpenAI.WhisperModel: The model to use for speech recognition (Speect-to-text can be powered by `whisper-1` for now).
* OpenAI.WhisperModelPrice: The [price of the model](https://openai.com/pricing) to use for speech recognition (per minute, in USD).
* OpenAI.Temperature: The temperature to use for generating responses.
* OpenAI.MaxTokens: The maximum number of tokens to use for generating responses.
* OpenAI.AudioFormat: The audio format to convert voice messages (`ogg`) to (can be `wav`, `mp3` or other supported by Whisper). Stated whithout a dot.
* OpenAI.SystemMessage: The message that will shape your bot's personality.

Configuration should be stored in the `./data/.config` file. Use the `config.example` file in the `./data` directory as a template.

## Running the Bot
To run the bot, simply run the command `python3 main.py`. The bot will start and will wait for messages. 
The bot has the following commands:
* `/start`: starts the conversation with the bot.
* `/help`: shows the help message.
* `/delete`: deletes the conversation history.
* `/statistics`: shows the bot usage.
* `/style`: changes the style of the bot from chat.
* Any other message (including voice message) will generate a response from the bot.

Users need to be whitelisted to use the bot. To whitelist yourself, send an access code to the bot using the `/start` command. The bot will then add you to the whitelist and will send a message to you confirming that you have been added to the whitelist.
Access code should be changed in the `./data/.config` file (see *Configuration*).
Codes are shown in terminal when the bot is started.

## Whitelisting users
To add yourself to the whitelist, send the bot a message with one of the access codes (see *Configuration*). The bot will then add you to the whitelist and will send a message to you confirming that.
Alternatively, you can add users to the whitelist manually. To do that, add the user's Telegram ID to the `./data/whitelist.txt` file. 
If no access codes are provided, anyone who not in the banlist will be able to use the bot.

## Banning Users
To ban a user you should add their Telegram ID to the `./data/banlist.txt` file. Each ID should be on a separate line. 
Banlist has a higher priority than the whitelist. If a user is on the banlist, they will not be able to use the bot and the will see a message saying that they have been banned.

## Deleting Conversation History
To delete the conversation history on the server, send the bot a message with the `/delete` command. The bot will then delete the conversation history and will send a message to you confirming that the history has been deleted. After that it will be a new conversation from the bot's point of view.
Conversation history in the Telegram chat will not be affected.

## Generating Responses
To generate a response, send the bot a message (or a voice message). The bot will then generate a response and send it back to you.

## Warinings
* The bot stores the whitelist in plain text. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot stores chat history in as a pickle file. The file is not encrypted and can be accessed by anyone with access to the server.
* Configurations are stored in plain text. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot can store messages in a log file in a event of an error. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot temporarily stores voice messages in `./data/voice` directory. The files are deleted after processing (successful or not), but can remain on the server if the event of an error. The files are not encrypted and can be accessed by anyone with access to the server.
* The bot is not designed to be used in production environments. It is not secure and was build as a proof of concept and for ChatGPT API testing purposes.
* Use this bot at your own risk. I am not responsible for any damage caused by this bot.

## License
This project is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) license. See the LICENSE file for more details.

## Acknowledgements
* [OpenAI ChatGPT API](https://platform.openai.com/docs/guides/chat) - The API used for generating responses.
* [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text) - The API used for speech recognition.
* [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - The library used for interacting with the Telegram API.
* [FFmpeg](https://ffmpeg.org/) - The library used for converting voice messages.
* [pydub](https://github.com/jiaaro/pydub) - The library used for finding the duration of voice messages.