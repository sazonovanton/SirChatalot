# Description: Main file for SirChatalot bot

# main libraries
import asyncio
import sys
import os
import time
from telegram import ForceReply, Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ChatAction
import codecs
import pickle
from functools import wraps

# For image processing
from PIL import Image
import base64
import io

# import configuration
import configparser
config = configparser.ConfigParser()
config.read('./data/.config', encoding='utf-8')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"
TOKEN = config.get("Telegram", "Token")
ratelimit_time = config.get("Telegram", "RateLimitTime") if config.has_option("Telegram", "RateLimitTime") else None
ratelimit_general = config.get("Telegram", "GeneralRateLimit") if config.has_option("Telegram", "GeneralRateLimit") else None
banlist_enabled = config.getboolean("Telegram", "EnableBanlist") if config.has_option("Telegram", "EnableBanlist") else False

# logging
import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-main")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/sirchatalot.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7,
                                       encoding='utf-8')
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)


logger.info('***** Starting chatbot... *****')
print('***** Starting chatbot... *****')

try:
    ratelimit_time = int(ratelimit_time)
except:
    logger.warning(f"Rate limit time is not a number ({ratelimit_time}). Setting it to None.")
    ratelimit_time = None

try:
    ratelimit_general = int(ratelimit_general)
except:
    logger.warning(f"General rate limit is not a number ({ratelimit_general}). Setting it to None.")
    ratelimit_general = None

# check if './data/rates.txt' exists
if not os.path.exists('./data/rates.txt'):
    logger.warning('File with rates does not exist.')
    rates_exists = False
else:
    rates_exists = True

if config.has_option("Telegram", "AccessCodes"):
    accesscodes = config.get("Telegram", "AccessCodes").split(',') 
    accesscodes = [x.strip() for x in accesscodes]
    print('Access codes: ' + ', '.join(accesscodes))
    print('-- Codes can be used to access the bot via sending it a message with a code. User will be added to a whitelist. Codes can be changed in the config file.\n')
else:
    accesscodes = None
    print('No access codes set. Bot will be available for everyone.\n')

if config.has_option("Telegram", "RateLimitTime"):
    print(f"Rate limit time: {config.get('Telegram', 'RateLimitTime')}")
    if config.has_option("Telegram", "GeneralRateLimit"):
        print(f"General rate limit: {config.get('Telegram', 'GeneralRateLimit')}") 
    else:
        print("No general rate limits.")
else:
    print("No rate limits.")

# check if file functionality is enabled
if config.has_section('Files'):
    files_enabled = True
else:
    files_enabled = False
if files_enabled:
    print('File functionality enabled.')

# check max file size
max_file_size_limit = 20
if config.has_option("Files", "MaxFileSizeMB"):
    max_file_size = config.get("Files", "MaxFileSizeMB")
    try:
        max_file_size = int(max_file_size)
        max_file_size = min(max_file_size, max_file_size_limit)
    except:
        max_file_size = max_file_size_limit
        logger.warning(f"Max file size is not a number. Setting it to {max_file_size_limit}.")
else:
    max_file_size = max_file_size_limit
    logger.warning(f"Max file size is not set. Setting it to {max_file_size_limit}.")

def get_rates():
    '''
    Get rates from the txt file
    Example of txt (user_id, number of requests per time stated in config file):
    123465,100
    456789,200
    '''
    try:
        user_rates = {}
        # if file exists, read it
        if os.path.exists('./data/rates.txt'):
            with codecs.open('./data/rates.txt', 'r', 'utf-8') as f:
                for line in f:
                    user_id, rate = line.split(',')
                    user_rates[int(user_id)] = int(rate)
        # if file does not exist, return None
        else:
            logger.debug('Rates file does not exist.')
            return None
        return user_rates
    except Exception as e:
        logger.exception('Could not get rates from file.')
        return None

if config.has_option("Telegram", "RateLimitTime"):
    user_rates = get_rates()
    if user_rates is not None and user_rates != {}:
        print(f"Limits for some ({len(user_rates)}) users are set (0 - unlimited).")
        for user_id, rate in user_rates.items():
            print(f"> User ID: {user_id}, limit: {rate}")
    else:
        print("No limits for users are set.")

print('-- If you want to learn more about limits please check description (README.md)\n')

from chatutils.processing import ChatProc
text_engine = config.get("Telegram", "TextEngine") if config.has_option("Telegram", "TextEngine") else "OpenAI"
speech_engine = config.get("Telegram", "SpeechEngine") if config.has_option("Telegram", "SpeechEngine") else "OpenAI"
gpt = ChatProc(text=text_engine, speech=speech_engine) # speech can be None if you don't want to use speech2text
VISION = gpt.vision
IMAGE_GENERATION = gpt.image_generation
from chatutils.filesproc import FilesProc
fp = FilesProc()

################################## Authorization ###############################################

def check_code(code, user_id) -> bool:
    '''
    Check if code is in accesscodes
    '''
    # check if code is in accesscodes
    try:
        if code in accesscodes:
            # add user to whitelist if code is correct
            with codecs.open("./data/whitelist.txt", "a", "utf-8") as f:
                f.write(str(user_id)+'\n')
            logger.info('Granted access to user with ID: ' + str(user_id) + '. Code used: ' + code)
            return True
    except Exception as e:
        logger.exception('Could not add user to whitelist. Code: ' + code + '. User ID: ' + str(user_id))
    return False

async def check_user(update, message=None, check_rate=True) -> bool:
    '''
    Check if user has an access
    '''
    # read banlist
    if banlist_enabled:
        try:
            with codecs.open("./data/banlist.txt", "r", "utf-8") as f:
                # Read the contents of the file into a list
                lines = f.readlines()
            banlist = [line.rstrip('\n') for line in lines]
        except:
            logger.exception('No banlist or it is not possible to read it')
            banlist = []

    # read whitelist
    if accesscodes is not None:
        try:
            with codecs.open("./data/whitelist.txt", "r", "utf-8") as f:
                # Read the contents of the file into a list
                lines = f.readlines()
            whitelist = [line.rstrip('\n') for line in lines]
        except:
            logger.warning('No whitelist or it is not possible to read it')
            whitelist = []

    user = update.effective_user
    # check if user is in banlist
    if banlist_enabled:
        if str(user.id) in banlist:
            logger.warning("Restricted access to banned user: " + str(user))
            await update.message.reply_text("You are banned.")
            return False

    # check there were no accesscodes provided in config file bot will be available for everyone not in banlist
    if accesscodes is None:
        return True

    # check if user is in whitelist
    if str(user.id) not in whitelist:
        # if not, check if user sent access code
        if message is not None:
            if check_code(message, user.id):
                # if yes, add user to whitelist and send welcome message
                await update.message.reply_text("You are now able to use this bot. Welcome!")
                # delete chat history
                success = await gpt.delete_chat(update.effective_user.id)
                if not success:
                    logger.info('Could not delete chat history for user: ' + str(update.effective_user.id))
                # send welcome message
                answer = await gpt.chat(id=user.id, message=rf"Hi! I'm {user.full_name}!")
                if answer is None:
                    answer = "Sorry, something went wrong. Please try again later."
                    logger.error('Could not get answer to start message')
                await update.message.reply_text(answer)
                return None
        await update.message.reply_text(rf"Sorry, {user.full_name}, you don't have access to this bot.")
        return False
    else:
        # check if user rate is limited
        if check_rate:
            ratecheck = await ratelimiter(user.id)
            if ratecheck == False:
                logger.info("Rate limited user: " + str(user))
                await update.message.reply_text("You are rate limited. You can check your limits with /limit")
                return False
        return True
    return True

# Decorator for authorization check
def is_authorized(func):
    '''
    Check if user is authorized to use the bot (in whitelist)
    Whitelist is stored in './data/whitelist.txt' file
    '''
    check_rate = True
    func_called = func.__name__
    if func_called in ['statistics_command', 'delete_command', 'limit_command']:
        logger.debug(f'Rate limit is not checked for function {func_called}')
        check_rate = False
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # check if user is in whitelist
        text = update.message.text if update.message is not None else None
        access = await check_user(update, text, check_rate=check_rate)
        logger.debug(f'Checking access for function {func_called}, rate check is {check_rate}, access is {access}')
        # if not, return
        if access != True:
            return
        # if yes, run the function
        return await func(update, context, *args, **kwargs)
    return wrapped

################################## Commands ###################################################

async def ratelimiter(user_id, check=False):
    '''
    Rate limiter for messages
    '''    
    # if ratelimit_time is None, 0 or '', return None
    if ratelimit_time is None or ratelimit_time <= 0:
        logger.debug(f'Rate is not limited for user {user_id}, ratelimit_time is {ratelimit_time} (None or <=0).')
        return None
    
    # get the limits for users
    if rates_exists:
        user_rates = get_rates()
    else:
        user_rates = None 

    # if user is in the dict, get the limit
    if user_rates is not None and user_rates != {}:
        if user_id in user_rates:
            limit = user_rates[user_id]
            if limit == 0:
                logger.debug(f'Rate is not limited for user {user_id}, limit is 0.')
                return None
        # if user is not in the dict, pass
        else:
            if ratelimit_general is None:
                logger.debug(f'Rate is not limited for user {user_id}, limit is not set for this user and general limit is None.')
                return None
            else:
                limit = int(ratelimit_general)
    else:
        if ratelimit_general is None:
            logger.debug(f'Rate is not limited for user {user_id}, limit is not set for this user and general limit is None.')
            return None
        else:
            limit = int(ratelimit_general)

    try:
        # open the pickle file with the dict if exists
        try:
            if os.path.exists('./data/tech/ratelimit.pickle'):
                with open('./data/tech/ratelimit.pickle', 'rb') as f:
                    rate = pickle.load(f)
            else:
                logger.info('No ratelimit.pickle file found. Creating a new one.')
                rate = {}
                with open('./data/tech/ratelimit.pickle', 'wb') as f:
                    pickle.dump(rate, f)
        except Exception as e:
            logger.error(f'Error while opening ratelimit.pickle. Error: {e}')
            rate = {}
        
        # create a function to check if user is in the dict
        if user_id not in rate:
            rate[user_id] = []
        # delete old values from the list 
        if len(rate[user_id]) > 0:
            rate[user_id] = [x for x in rate[user_id] if x > time.time() - ratelimit_time]
            # if the list is longer than the limit, return False
            if (len(rate[user_id]) > limit) and check != True:
                return False
        # add new value to the list
        if not check:
            rate[user_id].append(time.time())
        # save the dict to a pickle file
        with open('./data/tech/ratelimit.pickle', 'wb') as f:
            pickle.dump(rate, f)
        if check: 
            if len(rate[user_id]) > limit:
                return f"Rate limit of {limit} messages per {ratelimit_time} seconds exceeded. Please wait."
            return f"You have used your limit of {len(rate[user_id])}/{limit} messages per {ratelimit_time} seconds."
        return True
    except Exception as e:
        logger.exception('Could not create rate limiter. Rate is not limited.')
        return None

async def chat_modes_read(filepath='./data/chat_modes.ini'):
    '''
    Read chat modes from a ini file. Returns a dict with the chat mode names as keys and a dict with the description and system message as values.
    INI example:
        [Alice]
        Description = Alice is empathetic and friendly
        SystemMessage = You are a empathetic and friendly woman named Alice, who answers helpful, funny and a bit flirty.
    '''
    try:
        # read chat modes from file
        chat_modes = configparser.ConfigParser()
        chat_modes.read(filepath)
        # create a dict with chat modes
        modes = {}
        for mode in chat_modes.sections():
            modes[mode] = {
                'Desc': chat_modes[mode]['Description'],
                'SystemMessage': chat_modes[mode]['SystemMessage']
            }
        return modes
    except Exception as e:
        logger.exception('Could not read chat modes from file: ' + filepath)
        return None

# async def escaping(text):
#     special_chars = "_*[]()~`>#+-=|{}.!"
#     escaped_text = ""

#     for char in text:
#         if char in special_chars:
#             escaped_text += "\\" + char
#         else:
#             escaped_text += char
            
#     escaped_text = escaped_text.replace('"', '\\"')
#     return escaped_text

async def escaping(text):
   '''
   Inside (...) part of inline link definition, all ')' and '\' must be escaped with a preceding '\' character.
   In all other places characters:
   '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!' 
   must be escaped with the preceding character '\'.
   '''
   escaped = text.translate(str.maketrans({"-":  r"\-", "]":  r"\]", "^":  r"\^", "$":  r"\$", "*":  r"\*", ".":  r"\.", "!":  r"\!",
                                         "_":  r"\_", "[":  r"\[", "(":  r"\(", ")":  r"\)", "~":  r"\~", "`":  r"\`", ">":  r"\>",
                                           "#":  r"\#", "+":  r"\+", "=":  r"\=", "|":  r"\|", "{":  r"\{", "}":  r"\}",
                                           }))
   return escaped

async def send_message(update: Update, text, max_length=4096, markdown=0):
    '''
    Send a message to user, if too long - send it in parts
    '''
    try:
        # split text into parts
        parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        logger.debug(f'>> Text length: {len(text)}. Split into {len(parts)} parts (markdown={markdown}).')
        # send each part
        for index, part in enumerate(parts):
            if markdown == 0:
                await update.message.reply_text(part, reply_to_message_id=update.message.message_id if index == 0 else None)
            elif markdown == 1:
                try:
                    await update.message.reply_markdown(part, reply_to_message_id=update.message.message_id if index == 0 else None)
                except Exception as e:
                    logger.debug(f'(!) Error sending message (mk1 - {e}): {part}')
                    await send_message(update, part, markdown=2)
            elif markdown == 2:
                try:
                    esc_part = await escaping(part)
                    await update.message.reply_markdown_v2(esc_part, reply_to_message_id=update.message.message_id if index == 0 else None)
                except Exception as e:
                    logger.debug(f'(!) Error sending message (mk2 - {e}): {part}')
                    await update.message.reply_text(part, reply_to_message_id=update.message.message_id if index == 0 else None)
            else:
                # if markdown is not 0, 1 or 2, send message without markdown
                await update.message.reply_text(part, reply_to_message_id=update.message.message_id if index == 0 else None)
    except Exception as e:
        logger.exception('Could not send message to user: ' + str(update.effective_user.id))

################################## Commands ###################################################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message when the command /start is issued.
    '''
    user = update.effective_user
    # check if user is in whitelist
    access = await check_user(update, update.message.text)
    # if yes, send welcome message
    if access == True:
        answer = await gpt.chat(id=user.id, message=rf"Hi! I'm {user.full_name}!")
        if answer is None:
            answer = "Sorry, something went wrong. Please try again later."
            logger.error('Could not get answer to start message')
        await send_message(update, answer)
    else:
        logger.info("Restricted access to: " + str(user))

@is_authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message when the command /help is issued
    '''
    help_text = "This is a bot that allows you to chat with an AI.\n\n"
    help_text += "Commands:\n"
    help_text += "/start - Start the bot\n"
    help_text += "/help - Show this message\n"
    help_text += "/delete - Delete chat history\n"
    help_text += "/statistics - Show statistics\n"
    help_text += "/limit - Check user rate limit\n"
    help_text += "/style - Choose a style for a bot\n"
    help_text += "/imagine <prompt> - Generate an image\n" if IMAGE_GENERATION else ""
    help_text += "You can also send an image, bot has a multimodal chat functionality.\n" if VISION else ""
    help_text += "Some text files can be processed by the bot.\n" if files_enabled else ""
    help_text += "Bot will answer to your voice messages if you send them.\n" if speech_engine is not None else ""
    if gpt.function_calling:
        if gpt.webengine is not None:
            help_text += "\nYou can ask the bot to find something on the web. Just ask it to search for something. It will make request to a serach engine and will see a snippets of the first results. Example: `Find me a links to the best websites about cats.`\n"
        if gpt.urlopener is not None:
            help_text += "\nBot can also open a link for you, but this functionality is very limited. Example: `Summaraize the article from the link https://en.wikipedia.org/wiki/Cat_(Unix)`\n"
    if IMAGE_GENERATION:
        help_text += "\nImage generation is enabled. That means you can ask the bot to generate an image based on your prompt.\n"
        if gpt.function_calling:
            help_text += "\nYou can also just ask the bot to make an image. Example: `Draw a cat on a table for me.` or `Create a picture of a dog on a table.`\n" 
        if gpt.image_generation_engine_name == "dalle":
            help_text += "\nIf you want to control how the image is generated, you can use the following options in the prompt:\n"
            help_text += " `--natural` - for natural style\n `--vivid` - for vivid style\n `--revision` - for displaying a revised prompt\n `--horizontal` - for horizontal image\n `--vertical` - for vertical image\n"
            help_text += "\nExample: `/imagine a cat on a table --natural`\n"
        elif gpt.image_generation_engine_name == "stability":
            help_text += "\nIf you want to control how the image is generated, you can use the following options in the prompt:\n"
            help_text += " `--ratio 16:9` - for 16:9 aspect ratio (possible values: 1:1, 16:9, 21:9, 2:3, 3:2, 4:5, 5:4, 9:16, 9:21)\n `--negative <negative prompt>` - for negative prompt\n `--seed 0` - for seed value (postive integer, 0 for random)\n `--horizontal` - for horizontal image (16:9)\n `--vertical` - for vertical image (9:16)\n"
            help_text += "\nExample: `/imagine a cat on a table --ratio 2:3`\n"
        elif gpt.image_generation_engine_name == "yandex":
            help_text += "\nYou are using YandexART for image generation. For better results, you can follow YandexART [prompt library](https://yandex.cloud/ru/docs/foundation-models/prompts/yandexart/). You can add seed value with `--seed 42` (or any other number) to force the model to use the same seed for the image generation.\n"
            help_text += "\nExample: `/imagine a cat laying on the table, hd full wallpaper, sharp details, high quality, lots of details`\n"
        else:
            help_text += "\nExample: `/imagine a cat on a table`\n"
    await send_message(update, help_text, markdown=1)

@is_authorized
async def statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message with statistics when the command /statistics is issued
    '''
    stats_text = await gpt.get_stats(id=update.effective_user.id)
    if stats_text is None or stats_text == '':
        stats_text = "Sorry, there is no statistics yet or something went wrong. Please try again later."
        logger.error('Could not get statistics for user: ' + str(update.effective_user.id))
    await update.message.reply_text(stats_text)

@is_authorized
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Delete chat history when the command /delete is issued
    '''
    success = await gpt.delete_chat(update.effective_user.id)
    # send message about result
    if success:
        await update.message.reply_text("Chat history deleted")
    else:
        await update.message.reply_text("Sorry, it seems like there is no history with you.")
        logger.info('Could not delete chat history for user: ' + str(update.effective_user.id))

@is_authorized
async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Check user rate limit when the command /limit is issued
    '''
    user = update.effective_user
    text = await ratelimiter(user.id, check=True)
    if text is None:
        text = 'Unlimited'
    await update.message.reply_text(text)

################################## Messages ###################################################

@is_authorized
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Answer to user message
    '''
    global application
    # send typing action
    await application.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    answer = await gpt.chat(id=update.effective_user.id, message=update.message.text)
    # DEBUG
    logger.debug(f'>> Username: {update.effective_user.username}. Message: {update.message.text}')
    # add stats
    await gpt.add_stats(id=update.effective_user.id, messages_sent=1)
    # send message with a result
    if answer is None:
        answer = "Sorry, something went wrong. You can try later or /delete your session."
        logger.error('Could not get answer to message: ' + update.message.text)
    # TODO: function calling
    # if answer is base64, send it as a photo
    if type(answer) == tuple:
        if answer[0] == 'image':
            logger.debug(f'<< Username: {update.effective_user.username}. Answer - Image ({answer[2]}')
            image_bytes = base64.b64decode(answer[1])
            await update.message.reply_photo(photo=image_bytes)
            return None
    logger.debug(f'<< Username: {update.effective_user.username}. Answer: {answer}')
    await send_message(update, answer, markdown=1)

@is_authorized
async def answer_voice_or_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global application
    await application.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    if update.message.voice:
        file = update.message.voice
    elif update.message.video:
        file = update.message.video
    elif update.message.video_note:
        file = update.message.video_note
    else:
        await update.message.reply_text("Unsupported file type.")
        return

    file_id = file.file_id
    tg_file = await context.bot.get_file(file_id)
    file_extension = os.path.splitext(tg_file.file_path)[1]
    if not file_extension:
        # if voice message, use ogg extension, else mp4
        if update.message.voice:
            file_extension = '.ogg'
        else:
            file_extension = '.mp4'
    
    file_path = f'./data/voice/{file_id}{file_extension}'
    await tg_file.download_to_drive(custom_path=file_path)

    try:
        answer = await gpt.process_audio_video(id=update.effective_user.id, file_path=file_path)
    
        # Clean up file
        os.remove(file_path)
        logger.info(f'Audio/video file {file_path} was deleted')
    except Exception as e:
        logger.exception(f'Error processing audio/video file: {e}')
        answer = "Sorry, there was an error processing your audio/video file."

    if answer is None:
        answer = "Sorry, something went wrong. You can try later or /delete your session."
        logger.error(f'Could not get answer to voice/video message for user: {update.effective_user.id}')
    
    await send_message(update, answer, markdown=1)

@is_authorized
async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Sends a message with buttons attached when the command /style is issued. The buttons are used to choose a style for a bot.
    '''
    user = update.effective_user
    # read chat modes
    modes = await chat_modes_read()
    if modes is None:
        await update.message.reply_text('Sorry, something went wrong. Please try again later.')
        return None

    # generate keyboard with buttons
    k = []
    for name in modes.keys():
        k.append(InlineKeyboardButton(name, callback_data=name))
    keyboard = [
        k,
        [InlineKeyboardButton("[Default]", callback_data="default")],
    ]

    # send message with a keyboard
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = "Please choose a style for a bot.\n"
    msg += "You current chat session will be deleted.\n"
    msg += "Style is kept for the chat session until `/style` or `/delete` command is issued.\n"
    msg += "\n"
    msg += "Styles description:\n"

    # add styles description
    for name in modes.keys():
        msg += f"* {name}: {modes[name]['Desc']}\n"

    await update.message.reply_text(msg, reply_markup=reply_markup)

@is_authorized
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Handles the callback query when a button is pressed.
    '''
    user = update.effective_user
    # read chat modes
    modes = await chat_modes_read()
    if modes is None:
        await update.message.reply_text('Sorry, something went wrong. Please try again later.')
        return None

    # delete chat history
    query = update.callback_query
    # print(query)
    await query.answer()
    success = await gpt.delete_chat(update.effective_user.id)
    if success:
        logger.info('Deleted chat history for user for changing style: ' + str(update.effective_user.id))
    
    if query.data == "default":
        answer = await gpt.chat(id=user.id, message=rf"Hi, I'm {user.full_name}! Please introduce yourself.")
    else:
        answer = await gpt.chat(id=user.id, message=rf"Hi, I'm {user.full_name}! Please introduce yourself.", style=modes[query.data]['SystemMessage'])
    logger.info('Changed style for user: ' + str(update.effective_user.id) + ' to ' + str(query.data))

    if answer is None:
        answer = "Sorry, something went wrong. Please try again later."
        logger.error('Could not get answer for user: ' + str(update.effective_user.id))
    await query.edit_message_text(text=answer)

@is_authorized
async def save_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Saves the current chat session to a file.
    '''
    user = update.effective_user
    # save chat history
    success = await gpt.save_session(update.effective_user.id)
    if success:
        await update.message.reply_text("Chat session saved.")
    else:
        await update.message.reply_text("Sorry, something went wrong. Please try again later.")

@is_authorized
async def load_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Loads the chat session.
    '''
    user = update.effective_user
    # give user a choice of sessions
    sessions = await gpt.stored_sessions(update.effective_user.id)
    if sessions is None:
        await update.message.reply_text("Sorry, no stored sessions found. Please try again later.")
        return None

    # generate keyboard with buttons
    keyboard = []
    for name in sessions:
        keyboard.append(InlineKeyboardButton(name + str('...'), callback_data=name))
    keyboard = [keyboard]

    # send message with a keyboard
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = "Choose a session from stored ones.\n"

    await update.message.reply_text(msg, reply_markup=reply_markup)

@is_authorized
async def downloader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # check if file function is enabled
    if not files_enabled:
        await update.message.reply_text("Sorry, working with files is not supported at the moment.")
        return None

    global application
    try:
        file_id = update.message.document.file_id
        new_file = await application.bot.get_file(file_id)
        filename = new_file.file_path.split('/')[-1]
        filesize = new_file.file_size / 1024 / 1024 # file size in MB
        if filesize > max_file_size:
            await update.message.reply_text(f"Sorry, file size is too big. Please try again with a smaller file. Max file size is {max_file_size} MB.")
            return None
        new_file_path = await new_file.download_to_drive(custom_path='./data/files/' + filename)
        await application.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        logger.info('Recieved: ' + str(new_file_path))

        tic = time.time()
        text = await fp.extract_text(new_file_path)
        tt = round(time.time()-tic)
        logger.info('Process time: ' + str(tt) + ' seconds')

        if text is None or '':
            await update.message.reply_text("Sorry, something went wrong. Could not extract text from the file.")
            return None
        
        # if yes, get answer from GPT
        answer = await gpt.filechat(id=update.effective_user.id, text=text)
        if answer is None:
            answer = "Sorry, something went wrong. Could not get answer from GPT."
            logger.error('Could not get answer for user: ' + str(update.effective_user.id))
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Sorry, something went wrong while processing the file.")

################################## Images #####################################################
async def resize_image(image_bytes):
    '''
    Resize image from bytes by long side
    '''
    try:
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size
        new_width, new_height = width, height

        # Check if image conversion is needed
        if width > gpt.image_size or height > gpt.image_size:
            if width == height:
                new_width = gpt.image_size
                new_height = gpt.image_size
            if width > height:
                new_width = gpt.image_size
                new_height = int(height / width * new_width)
            else:
                new_height = gpt.image_size
                new_width = int(width / height * new_height)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Save image to base64 as jpg
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        logger.debug(f'>> Image resized from {width}x{height} to {new_width}x{new_height}')
        return image_base64
    except Exception as e:
        # if debug is enabled, save image to file
        try:
            if logger.level == logging.DEBUG:
                image = Image.open(io.BytesIO(image_bytes))
                image.save(f'./logs/{time.time()}.jpg')
                logger.debug(f'>> Image saved to file.')
        except Exception as e:
            logger.debug('>> Could not save image to file.')
        logger.error(e)
        return None

@is_authorized
async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    Process images - multimodal chat
    '''
    if not VISION:
        await update.message.reply_text("Sorry, working with images is not supported.")
        return None
    # Recieve image
    global application
    try:
        # image
        file_id = update.message.photo[-1].file_id
        new_file = await application.bot.get_file(file_id)
        image_bytes = await new_file.download_as_bytearray()

        # text (if sent along with image)
        text = update.message.caption

        # DEBUG
        logger.debug(f'>> Recieved image. Text with image: {text}')

        # Resize image
        image_base64 = await resize_image(image_bytes)

        # Send image to GPT Engine
        gpt_answer_image = await gpt.add_image(id=update.effective_user.id, image_b64=image_base64)
        if gpt_answer_image is False:
            await update.message.reply_text("Sorry, something went wrong with image processing.")
            return None
        
        if text is not None and text != '':
            # If text was sent along with image, send it to GPT Engine
            gpt_answer = await gpt.chat(id=update.effective_user.id, message=text)
        else:
            # If text was not sent along with image, ask user to send it
            if gpt_answer_image:
                await update.message.reply_text('Image recieved. I\'ll wait for your text before answering to it.')
                return None
            else:
                await update.message.reply_text('Sorry, something went wrong. Please contact the bot owner.')
                return None

        # If we recieve answer from GPT Engine, send it to user
        if gpt_answer is not None:
            await send_message(update, gpt_answer, markdown=1)
        else:
            await update.message.reply_text('Sorry, something went wrong. Please contact the bot owner.')
        
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Sorry, something went wrong while processing the image.")
    

@is_authorized
async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    Send a message with generated image when the command /imagine is issued
    Example: /imagine A cat on a table
    '''
    if not IMAGE_GENERATION:
        await update.message.reply_text("Sorry, image generation is not supported.")
        return None
    global application
    try:
        # send typing action
        await application.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        # get the prompt
        prompt = update.message.text.replace('/imagine', '').strip()
        # get the image
        image, text = await gpt.imagine(id=update.effective_user.id, prompt=prompt)
        if image is None and text is None:
            await update.message.reply_text('Sorry, something went wrong. Please contact the bot owner.')
            return None
        if text is not None and image is None:
            # we recieved only text
            await update.message.reply_text(text)
            return None
        # send the image (base64 to bytes)
        image_bytes = base64.b64decode(image)
        await update.message.reply_photo(photo=image_bytes, caption=text)
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Sorry, something went wrong while creating an image.")
    

###############################################################################################

def main() -> None:
    '''
    Start the bot.
    '''
    global application
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("statistics", statistics_command))
    application.add_handler(CommandHandler("limit", limit_command))

    # image generation
    application.add_handler(CommandHandler("imagine", imagine_command))

    # application.add_handler(CommandHandler("save_session", save_session_command))
    # application.add_handler(CommandHandler("load_session", load_session_command))
    # application.add_handler(CommandHandler("delete_session", delete_session_command))

    application.add_handler(CommandHandler("style", style_command))
    application.add_handler(CallbackQueryHandler(button))

    # on non command i.e message - answer the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
    application.add_handler(MessageHandler(filters.VOICE | filters.VIDEO | filters.VIDEO_NOTE, answer_voice_or_video))

    # recieve and process images
    application.add_handler(MessageHandler(filters.PHOTO, process_image))

    # download files
    application.add_handler(MessageHandler(filters.Document.Category('application/pdf'), downloader))
    application.add_handler(MessageHandler(filters.Document.Category('application/msword'), downloader))
    application.add_handler(MessageHandler(filters.Document.Category('application/vnd.openxmlformats-officedocument.wordprocessingml.document'), downloader))
    application.add_handler(MessageHandler(filters.Document.Category('application/vnd.ms-powerpoint'), downloader))
    application.add_handler(MessageHandler(filters.Document.Category('application/vnd.openxmlformats-officedocument.presentationml.presentation'), downloader))
    application.add_handler(MessageHandler(filters.Document.Category('text/plain'), downloader))

    # Run the bot until the Ctrl-C is pressed
    application.run_polling()


if __name__ == "__main__":
    main()

