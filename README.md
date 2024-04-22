# SirChatalot

This is a Telegram bot that can use various services to generate responses to messages.  

For text generation, the bot can use:
* OpenAI's [ChatGPT API](https://platform.openai.com/docs/guides/chat) (or other compatible API). Vision capabilities can be used with [GPT-4](https://platform.openai.com/docs/models/gpt-4-and-gpt-4-turbo) models. Function calling can be used with [Function calling](https://platform.openai.com/docs/guides/function-calling).
* Anthropic's [Claude API](https://docs.anthropic.com/claude/docs/text-generation). Vision capabilities can be used with [Claude 3](https://docs.anthropic.com/claude/docs/models-overview) models. Function calling can be used with [tool use](https://docs.anthropic.com/claude/docs/tool-use).
* [YandexGPT API](https://yandex.cloud/ru/docs/yandexgpt/)

Bot can also generate images with:
* OpenAI's [DALL-E](https://platform.openai.com/docs/guides/images)
* [Stability AI](https://platform.stability.ai/)
* [Yandex ART](https://yandex.cloud/ru/docs/foundation-models/quickstart/yandexart)

This bot can also be used to generate responses to voice messages. Bot will convert the voice message to text and will then generate a response. Speech recognition can be done using the OpenAI's [Whisper model](https://platform.openai.com/docs/guides/speech-to-text). To use this feature, you need to install the [ffmpeg](https://ffmpeg.org/) library. Voice message support won't work without it.  
This bot is also support working with files, see [Files](#files) section for more details.  

If function calling is enabled, bot can generate images and [search the web](#web-search) (limited).

## Navigation
* [Getting Started](#getting-started)
* [Configuration](#configuration)
* [Using Claude](#using-claude)
* [Using YandexGPT](#using-yandexgpt)
* [Vision](#vision)
* [Image generation](#image-generation)
* [Web Search](#web-search)
* [Function calling](#function-calling)
* [Using OpenAI compatible APIs](#using-openai-compatible-apis)
* [Styles](#styles)
* [Files](#files)
* [Running the Bot](#running-the-bot)
* [Whitelisting users](#whitelisting-users)
* [Banning Users](#banning-users)
* [Safety practices](#safety-practices)
* [Rate limiting users](#rate-limiting-users)
* [Using Docker](#using-docker)
* [Read messages](#read-messages)
* [Warinings](#warinings)
* [License](#license)
* [Acknowledgements](#acknowledgements)

## Getting Started
* Create a bot using the [BotFather](https://t.me/botfather).
* Clone the repository.
* Install the required packages by running the command `pip install -r requirements.txt`.
* Install the [ffmpeg](https://ffmpeg.org/) library for voice message support (for converting .ogg files to other format) and test it calling `ffmpeg --version` in the terminal. Voice message support won't work without it.
* If you use Linux - install `catdoc` for `.doc` and `.ppt` files support and test it calling `catdoc` in the terminal. `.doc` and `.ppt` files support won't work without it.  
If you use Windows - install `comtypes` for `.doc` and `.ppt` files support with `pip install comtypes`.
* Create a `.config` file in the `data` directory using the `config.example` file in that directory as a template.
* Run the bot by running the command `python3 main.py`.

`Whitelist.txt`, `banlist.txt`, `.config`, `chat_modes.ini`, are stored in the `./data` directory. Logs rotate every day and are stored in the `./logs` directory.

Bot is designed to talk to you in a style of a knight in the middle ages by default. You can change that in the `./data/.config` file (SystemMessage).

There are also some additional styles that you can choose from: Alice, Bob, Charlie and Diana. You can change style from chat by sending a message with `/style` command, but your current session will be dropped. 
Styles can be set up in the `./data/chat_modes.ini` file. You can add your own styles there or change the existing ones.

## Configuration
The bot requires a configuration file to run. The configuration file should be in [INI file format](https://en.wikipedia.org/wiki/INI_file). Example configuration file is in the `./data` directory.  
File should contain (for OpenAI API):
```ini
[Telegram]
Token = 0000000000:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AccessCodes = whitelistcode,secondwhitelistcode
RateLimitTime = 3600
GeneralRateLimit = 100
TextEngine = OpenAI

[Logging]
LogLevel = WARNING
LogChats = False

[OpenAI]
SecretKey = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ChatModel = gpt-3.5-turbo-0125
ChatModelPromptPrice = 0.0015
ChatModelCompletionPrice = 0.002
WhisperModel = whisper-1
WhisperModelPrice = 0.006
Temperature = 0.7
MaxTokens = 3997
MinLengthTokens = 100
AudioFormat = wav
SystemMessage = You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages.
MaxSessionLength = 15
ChatDeletion = False
EndUserID = True
Moderation = False
Vision = False
ImageSize = 512
FunctionCalling = False
DeleteImageAfterAnswer = False
ImageDescriptionOnDelete = False
SummarizeTooLong = False

[Files]
Enabled = True
MaxFileSizeMB = 10
MaxSummaryTokens = 1000
MaxFileLength = 10000
DeleteAfterProcessing = True
```
Telegram:
* Telegram.Token: The token for the Telegram bot.
* Telegram.AccessCodes: A comma-separated list of access codes that can be used to add users to the whitelist. If no access codes are provided, anyone who not in the banlist will be able to use the bot.
* Telegram.RateLimitTime: The time in seconds to calculate user rate-limit. Optional.
* Telegram.GeneralRateLimit: The maximum number of messages that can be sent by a user in the `Telegram.RateLimitTime` period. Applied to all users. Optional.
* Telegram.TextEngine: The text engine to use. Optional, default is `OpenAI`. Other options are `YandexGPT` and `Claude`.
* Logging.LogLevel: The logging level. Optional, default is `WARNING`.
* Logging.LogChats: If set to `True`, bot will log all chats. Optional, default is `False`.

OpenAI:
* OpenAI.SecretKey: The secret key for the OpenAI API.
* OpenAI.ChatModel: The model to use for generating responses (`gpt-3.5-turbo`, `gpt-3.5-turbo-16k` are available for [GPT-3.5](https://platform.openai.com/docs/models/gpt-3-5), `gpt-4`, `gpt-4-32k` are available for [GPT-4](https://platform.openai.com/docs/models/gpt-4)).
* OpenAI.ChatModelPrice: The [price of the model](https://openai.com/pricing) to use for generating responses (per 1000 tokens, in USD).
* OpenAI.WhisperModel: The model to use for speech recognition (Speect-to-text can be powered by `whisper-1` for now).
* OpenAI.WhisperModelPrice: The [price of the model](https://openai.com/pricing) to use for speech recognition (per minute, in USD).
* OpenAI.Temperature: The temperature to use for generating responses.
* OpenAI.MaxTokens: The maximum number of tokens to use for generating responses.
* OpenAI.MinLengthTokens: The minimum number of tokens to use for generating responses. Optional, default 100.
* OpenAI.AudioFormat: The audio format to convert voice messages (`ogg`) to (can be `wav`, `mp3` or other supported by Whisper). Stated whithout a dot.
* OpenAI.SystemMessage: The message that will shape your bot's personality.
* OpenAI.MaxSessionLength: The maximum number of user messages in a session (can be used to reduce tokens used). Optional.
* OpenAI.ChatDeletion: Whether to delete the user's history if conversation is too long. Optional.
* OpenAI.EndUserID: Whether to add the user's ID to the API request. Optional.
* OpenAI.Moderation: Whether to use the OpenAI's moderation engine. Optional.
* OpenAI.Vision: Whether to use vision capabilities of GPT-4 models. Default: `False`. See [Vision](#vision).
* OpenAI.ImageSize: Maximum size of images. If image is bigger than that it will be resized. Default: `512`
* OpenAI.DeleteImageAfterAnswer: Whether to delete image after it was seen by model. Enable it to keep cost of API usage low. Default: `False`.
* OpenAI.ImageDescriptionOnDelete: Whether to replace image with it description after it was deleted (see `OpenAI.DeleteImageAfterAnswer`). Default: `False`.
* OpenAI.FunctionCalling: Whether to use function calling capabilities (see section [Function calling](#function-calling)). Default: `False`.
* OpenAI.SummarizeTooLong: Whether to summarize first set of messages if session is too long instead of deleting it. Default: `False`.

Files:
* Files.Enabled: Whether to enable files support. Optional. Default: `True`.
* Files.MaxFileSizeMB: The maximum file size in megabytes. Optional. Default: `20`.
* Files.MaxSummaryTokens: The maximum number of tokens to use for generating summaries. Optional. Default: `OpenAI.MaxTokens`/2.
* Files.MaxFileLength: The maximum number of tokens to use for generating summaries. Optional. Default: `10000`.
* Files.DeleteAfterProcessing: Whether to delete files after processing. Optional. Deafult: `True`.

Configuration should be stored in the `./data/.config` file. Use the `config.example` file in the `./data` directory as a template.  
Claude and YandexGPT configurations are different, see [Using Claude](#using-claude-anthropic-api) and [Using YandexGPT](#using-yandexgpt) sections for more details.

## Using Claude
Claude is a family of large language models developed by [Anthropic](https://www.anthropic.com/). You should [get access](https://docs.anthropic.com/claude/docs/getting-access-to-claude) to it first.   
You need to install [Anthropic's Python SDK](https://github.com/anthropics/anthropic-sdk-python) beforehand by running:
```bash
pip install anthropic
```  
To use Claude, you need to change the `Telegram.TextEngine` field to `Claude` or `Anthropic` in the `./data/.config` file and replace the `OpenAI` section with `Anthropic` section:
```ini
[Telegram]
Token = 111111111:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AccessCodes = 123456789
TextEngine = Claude

[Anthropic]
SecretKey = sk-ant-******
ChatModel = claude-3-haiku-20240307
ChatModelPromptPrice = 0.00025
ChatModelCompletionPrice = 0.00125
Temperature = 0.7
MaxTokens = 1500
SystemMessage = You are a librarian named Bob whom one may met in tavern. You a chatting with user via Telegram messenger.
Vision = True
ImageSize = 768
DeleteImageAfterAnswer = False
ImageDescriptionOnDelete = False
SummarizeTooLong = True
FunctionCalling = False
```

* Anthropic.SecretKey: The secret key for the Anthropic API.
* Anthropic.ChatModel: The model to use for generating responses (`claude-3-haiku-20240307` by default).
* Anthropic.ChatModelPromptPrice: The price of the model to use for generating responses (per 1000 tokens, in USD).
* Anthropic.ChatModelCompletionPrice: The price of the model to use for generating responses (per 1000 tokens, in USD).
* Anthropic.Temperature: The temperature to use for generating responses.
* Anthropic.MaxTokens: The maximum number of tokens to use for generating responses.
* Anthropic.SystemMessage: The message that will shape your bot's personality.
* Anthropic.Vision: Whether to use vision capabilities of Claude 3 models. Default: `False`.
* Anthropic.ImageSize: Maximum size of images. If image is bigger than that it will be resized. Default: `512`
* Anthropic.DeleteImageAfterAnswer: Whether to delete image after it was seen by model. Enable it to keep cost of API usage low. Default: `False`.
* Anthropic.ImageDescriptionOnDelete: Whether to replace image with it description after it was deleted (see `OpenAI.DeleteImageAfterAnswer`). Default: `False`.
* Anthropic.SummarizeTooLong: Whether to summarize first set of messages if session is too long instead of deleting it. Default: `False`.
* Anthropic.FunctionCalling: Whether to use function calling capabilities (see section [Function calling](#function-calling)). Default: `False`.

You can find Claude models [here](https://docs.anthropic.com/claude/docs/models-overview).

You can also set up HTTP proxy for API requests in the `./data/.config` file (tested) like this:
```ini
[Anthropic]
...
Proxy = http://login:password@proxy:port
...
```  
Example of configuration for using Claude API is in the `./data/config.claude.example` file.

## Using YandexGPT
YandexGPT is in Preview, you should request access to it.  
You should have a service Yandex Cloud account to use YandexGPT (https://yandex.cloud/en/docs/yandexgpt/quickstart). Service account should have access to the YandexGPT API and role `ai.languageModels.user` or higher.    
To use YandexGPT, you need to set the `Telegram.TextEngine` field to `YandexGPT` in the `./data/.config` file:
```ini
[Telegram]
Token = 111111111:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AccessCodes = 123456789
TextEngine = YandexGPT

[YandexGPT]
SecretKey=******
CatalogID=******
ChatModel=gpt://<CatalogID>/yandexgpt/latest
Temperature=700
MaxTokens=1500
SystemMessage=You are a helpful assistant named Sir Chatalot.
SummarizeTooLong = True
RequestLogging = False
```  
* YandexGPT.SecretKey: The secret key for the Yandex Cloud.
* YandexGPT.CatalogID: The catalog ID for the Yandex Cloud.
* YandexGPT.Endpoint: The endpoint for the Yandex GPT API. Optional, default is `https://llm.api.cloud.yandex.net/foundationModels/v1/completion`.
* YandexGPT.ChatModel: The model to use for generating responses (learn more [here](https://yandex.cloud/en/docs/yandexgpt/concepts/models)). You can use `gpt://<CatalogID>/yandexgpt-lite/latest` or just `yandexgpt-lite/latest` (default) for the latest model in the default catalog.
* YandexGPT.ChatModelCompletionPrice: The price of the model to use for generating responses (per 1000 tokens, in USD).
* YandexGPT.ChatModelPromptPrice: The price of the model to use for generating responses (per 1000 tokens, in USD).
* YandexGPT.SummarisationModel: The model to use for summarisation. Optional, default is `summarization/latest`.
* YandexGPT.Temperature: The temperature to use for generating responses.
* YandexGPT.MaxTokens: The maximum number of tokens to use for generating responses.
* YandexGPT.SystemMessage: The message that will shape your bot's personality.
* YandexGPT.SummarizeTooLong: Whether to summarize first set of messages if session is too long instead of deleting it. Default: `False`.
* YandexGPT.RequestLogging: Whether to disable logging of API requests by the Yandex Cloud (learn more [here](https://yandex.cloud/en/docs/yandexgpt/operations/disable-logging)). Default: `False`.

YandexGPT support is experimental, please submit an issue if you find a problem. It was rewritten to use YandexGPT v1 instead of v1alpha due to v1alpha [deprecation](https://yandex.cloud/en/docs/yandexgpt/api-ref/migration-to-v1).

> [!WARNING]
> There were some changes for YandexGPT. If you have an old configuration file, please update it to the new format. 

## Vision
Bot can understand images with [OpenAI GPT-4](https://platform.openai.com/docs/guides/vision) or [Claude 3](https://docs.anthropic.com/claude/docs/vision) models.  
To use this functionality you should make some changes in configuration file  (change OpenAI to Anthropic if you use Claude).    
Example:  
```ini
...
[OpenAI]
ChatModel = gpt-4-vision-preview
ChatModelPromptPrice = 0.01
ChatModelCompletionPrice = 0.03
...
Vision = True
ImageSize = 512
DeleteImageAfterAnswer = False
ImageDescriptionOnDelete = False
...
```  
Check if you have an access to GPT-4V or Claude 3 models with vision capabilities.  
OpenAI models can be found [here](https://platform.openai.com/docs/models/gpt-4) and prices can be found [here](https://openai.com/pricing).   
Claude 3 models and prices can be found [here](https://docs.anthropic.com/claude/docs/models-overview).

Beware that right now functionalty for calculating cost of usage is not working for images, so you should pay attenion to that.   

## Function calling
You can use function calling capabilities with some [OpenAI](https://platform.openai.com/docs/guides/function-calling) or [Claude](https://docs.anthropic.com/claude/docs/tool-use) models.   
This way model will decide what function to call by itself. For example, you can ask the bot to generate an image and it will do it.  
Right now image generation and some web tools are supported.  
To use this functionality you should make some changes in configuration file. Example (OpenAI, for Claude change OpenAI to Anthropic):    
```ini
...
[OpenAI]
FunctionCalling = True
...
```
Don't forget to enable Image generation (see [Image generation](#image-generation)).  
This feature is experimental, please submit an issue if you find a problem.  

## Image generation
You can generate images. Right now only [DALL-E](https://platform.openai.com/docs/guides/images) and [Stability AI](https://platform.stability.ai/) are supported.  

To generate an image, send the bot a message with the `/imagine <text>` command. The bot will then generate an image based on the text prompt. Images are not stored on the server and processed as base64 strings.  
Also if `FunctionCalling` is set to `True` in the `./data/.config` file (see [Function calling](#function-calling)), you can generate images with function calling just by asking the bot to do it.  

`RateLimitCount`, `RateLimitTime` and `ImageGenerationPrice` parameters are not required, default values for them are zero. So if not set rate limit will not be applied and price will be zero.  

### OpenAI DALL-E
To use this functionality with Dall-E you should make some changes in configuration file. Example:  
```ini
...
[ImageGeneration]
Engine = dalle
APIKey = ******
Model = dall-e-3
RateLimitCount = 16
RateLimitTime = 3600
ImageGenerationPrice = 0.04
...
```  
If you want to use OpenAI text engine and image generation you can omit `APIKey` field in the `ImageGeneration` section. Key will be taken from the `OpenAI` section.  
For OpenAI you can also set `BaseURL` field in the `ImageGeneration` section. If it was set in `OpenAI` section, it will be used instead, to override it you cat set `ImageGeneration.BaseURL` to `None`.  
Parameters set in `ImageGeneration` have priority over `OpenAI` section for image generation.  

**Alternatively** you can set up DALL-E in OpenAI section of the `./data/.config` file (deprecated, support can be removed in the future).  
If config has section `ImageGeneration` it will be used instead and this method will be ignored.  
```ini
...
ImageGeneration = False
ImageGenModel = dall-e-3
ImageGenerationSize = 1024x1024
ImageGenerationStyle = vivid
ImageGenerationPrice = 0.04
...
```
### Stability AI
To use this functionality with Stability AI you should make some changes in configuration file. Example:  
```ini
[ImageGeneration]
Engine = stability
ImageGenURL = https://api.stability.ai/v2beta/stable-image/generate/core
APIKey = ******
ImageGenerationRatio = 1:1
RateLimitCount = 16
RateLimitTime = 3600
ImageGenerationPrice = 0.04
```  
You can also set `NegativePrompt` (str) and `Seed` (int) parameters in the `ImageGeneration` section if you want to use them.  
`ImageGenURL` and `ImageGenerationRatio` are not required, default values (in example) are used if they are not set.  

### Yandex ART
To use this functionality with Yandex ART you should add a section in the configuration file. Example:  
```ini
[ImageGeneration]
Engine = yandex
APIKey = ******
ImageGenModel = yandex-art/latest
CatalogID = ******
RateLimitCount = 5
RateLimitTime = 3600    
```
`ImageGenModel` can also have a value `art://<CatalogID>/yandex-art/latest`.  
You can also set `ImageGenerationPrice` (float) parameter in the `ImageGeneration` section if you want to use it. Also you can fix seed for image generation by setting `Seed` (int) parameter.  
Service Yandex Foundation Models is on Preview, stage so it can be unstable.  
YandexART API demands IAM token for requests. Service account should have access to the Yandex ART API and role `ai.imageGeneration.user` or higher.  
Learn more about Yandex ART [here](https://yandex.cloud/ru/docs/foundation-models/quickstart/yandexart) (ru).

## Web Search
You can use web search capabilities with function calling.  
Right now only Google search is supported (via [Google Search API](https://developers.google.com/custom-search/v1/overview)).  
To enable web search you should make some changes in configuration file. Example:  
```ini
...

[Web]
SearchEngine = google
APIKey = ******
CSEID = ******
URLSummary = False
TrimLength = 3000
...
```  
Keep in mind that you should also set `FunctionCalling` to `True` in the `./data/.config` file (see [Function calling](#function-calling)).  
If `SearchEngine` is not set, web search functionality will not be enabled.  
SirChatalot will only have information about the first 5 results (title, link and description).  
It can try to open only links provided (or from history), but will not walk through the pages when using web search.  
`URLSummary` parameter is used to tell the bot to summarize the content of the page.   
`TrimLength` is used to limit the length of the parsed text (context can be lost).  

## Using OpenAI compatible APIs
You can use APIs compatible with OpenAI's API. To do that, you need to set endpoint in the `OpenAI` section of the `./data/.config` file:
```ini
[OpenAI]
...
APIBase = https://xxxxxxxxxxxxxxx.proxy.runpod.net/
SecretKey = myapikey
ChatModel = gpt-3.5-turbo
Temperature = 0.7
Moderation = False
...
```
Also it is possible to set `APIType` and `APIVersion` fields in the `./data/.config` file.  
All this values are optional. Do not set them if you don't know what they are.  
Library [openai-python](https://github.com/openai/openai-python) is used for API requests.  
Tested with [LocalAI](https://github.com/mudler/LocalAI). Vision is still untested for alternative APIs.  

## Styles
Bot supports different styles that can be triggered with `/style` command.  
You can add your own style in the `./data/chat_modes.ini` file or change the existing ones. Styles are stored in the INI file format.  
Example:
```
[Alice]
Description = Empathetic and friendly
SystemMessage = You are a empathetic and friendly woman named Alice, who answers helpful, funny and a bit flirty.

[Bob]
Description = Brief and informative
SystemMessage = You are a helpful assistant named Bob, who is informative and explains everything succinctly with fewer words.

```
Here is a list of the fields in this example:
* Alice or Bob: The name of the style. 
* Description: Short description of the style. Is used in message that is shown when `/style` command is called.
* SystemMessage: The message that will shape your bot's personality. You will need some prompt engineering to make it work properly.

## Files
Bot supports working with files. You can send a file to the bot and it will send back a response based on the file's extracted text.  
It can work quite poorly with some files, create an issue if you find a problem.  
Files temporarily stored in the `./data/files` directory. After successful processing, they are deleted if other behavior is not specified in the `./data/.config` file.  
Currently supported file types: `.docx`, `.doc`, `.pptx`, `.ppt`, `.pdf`, `.txt`.  
Maximum file size to work with is 20 MB (`python-telegram-bot` limitation), you can set your own limit in the `./data/.config` file (in MB), but it will be limited by the `python-telegram-bot` limit.  
If file is too large, the bot will attempt to summarize it to the length of MaxTokens/2. You can set your own limit in the `./data/.config` file (in tokens - one token is ~4 characters).    
You can also limit max file lenght (in characters) by setting the `Files.MaxFileLength` field in the `./data/.config` file (in tokens). It can be set because sumarization is made with API requests and it can be expensive.  
Summarisation will happen by chunks of size `Files.MaxSummaryTokens` until the whole file is processed. Summary for chunks will be combined into one summary (maximum 3 itterations, then text is just cut).      

You can disable files support in the `./data/.config` file by setting `Files.Enabled` to `False`.

## Running the Bot
To run the bot, simply run the command `python3 main.py`. The bot will start and will wait for messages. 
The bot has the following commands:
* `/start`: starts the conversation with the bot.
* `/help`: shows the help message.
* `/delete`: deletes the conversation history.
* `/statistics`: shows the bot usage.
* `/style`: changes the style of the bot from chat.
* `/limit`: shows the current rate-limit for the user.
* `/imagine <text>`: generates an image based on the text. You can use it only if `OpenAI.ImageGeneration` is set to `True` (see *Image generation*).
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

## Safety practices
To prevent the bot from being used for purposes that violate the OpenAI's usage policy, you can use:
* Moderation: Moderation will filter out messages that can violate the OpenAI's usage policy with free OpenAI's [Moderation API](https://platform.openai.com/docs/guides/moderation). In this case, message is sent to the Moderation API and if it is flagged, it is not sent to the OpenAI's API. If you want to use it, set `OpenAI.Moderation` to `true` in the `./data/.config` file (see *Configuration*). User will be notified if their message is flagged.
* End-user IDs: End-user IDs will be added to the API request if `OpenAI.EndUserID` is set to `true` in the `./data/.config` file (see *Configuration*). Sending end-user IDs in your requests can be a useful tool to help OpenAI monitor and detect abuse. This allows OpenAI to provide your team with more actionable feedback in the event of bot abuse. End-user ID is a hashed Telegram ID of the user.
* Rate limiting: Rate limiting will limit the number of messages a user can send to the bot. If you want to use it, set `Telegram.GeneralRateLimit` to a number of messages a user can send to the bot in a time period in the `./data/.config` file (see *Configuration*). 
* Banlist: Banlist will prevent users from using the bot. If you want to use it, add user's Telegram ID to the `./data/banlist.txt` file (see *Banning Users*).
* Whitelist: Whitelist will allow only whitelisted users to use the bot. If you want to use it, add user's Telegram ID to the `./data/whitelist.txt` file (see *Whitelisting Users*).

## Rate limiting users
To limit the number of messages a user can send to the bot, add their Telegram ID and limit to the `./data/rates.txt` file. Each ID should be on a separate line.
Example:
```ini
123456789,10
987654321,500
111111,0
```
Rate limit is a number of messages a user can send to the bot in a time period. In example user with ID 123456789 has 10 and user 987654321 has 500 messages limit. User 111111 has no limit (overriding `GeneralRateLimit`).  
Time period (in seconds) can be set in the `./data/.config` file in `RateLimitTime` variable in `Telegram` section (see *Configuration*). If no time period is provided, limit is not applied.  
General rate limit can be set in the `./data/.config` file in `GeneralRateLimit` variable in `Telegram` section (see *Configuration*). If no general rate limit is provided, limit is not applied for users who are not in the `rates.txt` file. To override general rate limit for a user, set their limit to 0 in the `rates.txt` file.  
Users can check their limit by sending the bot a message with the `/limit` command. 

## Using Docker
You can use Docker to run the bot. You need to build the image first. To do that, run the following command in the root directory of the project after configuring the bot (see *Configuration*):
```bash
docker compose up -d
```
This will build the image and run the container. You can then use the bot as described above.  
To rebuild the image add `--build` flag to the command:
```bash
docker compose up -d --build
```
If you are using custo docker-compose file, you can use it like this:
```bash
docker compose -f docker-compose.yml up -d --build
```
To stop the container, run the following command:
```bash
docker compose down
```

## Read messages
You can read user messages for moderation purposes with `read_messages.py`.  
Call it from projects `chatutils` directory with:
```bash
python3 read_messages.py
```  

## Warinings
* The bot stores the whitelist in plain text. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot stores chat history in as a pickle file. The file is not encrypted and can be accessed by anyone with access to the server.
* Configurations are stored in plain text. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot can store messages in a log file in a event of an error. The file is not encrypted and can be accessed by anyone with access to the server.
* The bot temporarily stores voice messages in `./data/voice` directory. The files are deleted after processing (successful or not), but can remain on the server if the event of an error. The files are not encrypted and can be accessed by anyone with access to the server.
* The bot is not designed to be used in production environments. It is not secure and was build as a proof of concept and for ChatGPT API testing purposes.
* The bot will try to continue conversation in the event of reaching maximum number of tokens by trimming the conversation history or summarazing it (`SummarizeTooLong`). If the conversation is long enough to cause errors, it will be deleted if `ChatDeletion` set to `True` in the `./data/.config` file (see *Configuration*).
* The bot is using a lot of read and write operations with pickle files right now. This can lead to a poor performance on some servers if the bot is used by a lot of users. Immediate fix for that is mounting the `./data/tech` directory as a RAM disk, but in a event of a server shutdown, all data will be lost.
* The bot can work with files. If file was not processed or `Files.DeleteAfterProcessing` is set to `False` in the `./data/.config` file (see *Configuration*), the file will be stored in `./data/files` directory. The files are not encrypted and can be accessed by anyone with access to the server.
* If message is flagged by the OpenAI Moderation API, it will not be sent to the OpenAI's API, but it will be stored in `./data/moderation.txt` file for manual review. The file is not encrypted and can be accessed by anyone with access to the server.
* Use this bot at your own risk. I am not responsible for any damage caused by this bot.
* Functionalty for calculating cost of usage is not working for images for now, so you should pay attenion to that.   
* /delete command will delete conversation history on the server. It will not affect the conversation history in the Telegram chat. 

## License
This project is licensed under [GPLv3](https://www.gnu.org/licenses/gpl-3.0.en.html). See the `LICENSE` file for more details.

## Acknowledgements
* [OpenAI ChatGPT API](https://platform.openai.com/docs/guides/chat) - The API used for generating responses.
* [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text) - The API used for speech recognition.
* [OpenAI DALL-E API](https://platform.openai.com/docs/guides/images) - The API used for generating images.
* [Yandex GPT API](https://cloud.yandex.ru/docs/yandexgpt/) - The API used for generating responses.
* [Anthropic Claude API](https://docs.anthropic.com/claude/docs/text-generation) - The API used for generating responses.
* [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - The library used for interacting with the Telegram API.
* [FFmpeg](https://ffmpeg.org/) - The library used for converting voice messages.
* [pydub](https://github.com/jiaaro/pydub) - The library used for finding the duration of voice messages.
