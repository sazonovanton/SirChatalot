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

# logging
import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-main")
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
TOKEN = config.get("Telegram", "Token")
ratelimit_time = config.get("Telegram", "RateLimitTime") if config.has_option("Telegram", "RateLimitTime") else None
ratelimit_general = config.get("Telegram", "GeneralRateLimit") if config.has_option("Telegram", "GeneralRateLimit") else None
banlist_enabled = config.getboolean("Telegram", "EnableBanlist") if config.has_option("Telegram", "EnableBanlist") else False

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
if config.has_option("Files", "Enabled"):
    files_enabled = config.getboolean('Files', 'Enabled')   
else:
    files_enabled = True
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

legacy_mode = False
if config.has_option("Telegram", "LegacyMode"):
    legacy_mode = config.getboolean("Telegram", "LegacyMode")
if legacy_mode:
    print('(!) Legacy mode is enabled. Bot will use legacy mode for processing messages.\n')
    from gptproc import GPT
    gpt = GPT()
else:
    from processing import ChatProc
    gpt = ChatProc(text="OpenAI", speech="OpenAI")
from filesproc import FilesProc
fp = FilesProc()

###############################################################################################

def ratelimiter(user_id, check=False):
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
            with open('./data/tech/ratelimit.pickle', 'rb') as f:
                rate = pickle.load(f)
        # if file does not exist, create an empty dict
        except Exception as e:
            logger.warning(f'Error while opening ratelimit.pickle. Creating and saving an empty dict. Exception: {e}')
            rate = {}
            # save the dict to a pickle file
            with open('./data/tech/ratelimit.pickle', 'wb') as f:
                pickle.dump(rate, f)
        
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


def chat_modes_read(filepath='./data/chat_modes.ini'):
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

def escaping(text):
    '''
    Inside (...) part of inline link definition, all ')' and '\' must be escaped with a preceding '\' character.
    In all other places characters:
    '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!' 
    must be escaped with the preceding character '\'.
    '''
    escaped = text.translate(str.maketrans({"-":  r"\-",
                                          "]":  r"\]",
                                          "^":  r"\^",
                                          "$":  r"\$",
                                          "*":  r"\*",
                                          ".":  r"\.",
                                          "!":  r"\!",
                                          "_":  r"\_",
                                          "[":  r"\[",
                                            "(":  r"\(",
                                            ")":  r"\)",
                                            "~":  r"\~",
                                            "`":  r"\`",
                                            ">":  r"\>",
                                            "#":  r"\#",
                                            "+":  r"\+",
                                            "=":  r"\=",
                                            "|":  r"\|",
                                            "{":  r"\{",
                                            "}":  r"\}",
                                            }))
    return escaped

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message when the command /start is issued.
    '''
    user = update.effective_user
    # check if user is in whitelist
    access = await check_user(update, update.message.text)
    # if yes, send welcome message
    if access == True:
        answer = gpt.chat(id=user.id, message=rf"Hi! I'm {user.full_name}!")
        if answer is None:
            answer = "Sorry, something went wrong. Please try again later."
            logger.error('Could not get answer to start message: ' + update.message.text)
        await update.message.reply_text(answer)
    else:
        logger.info("Restricted access to: " + str(user))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message when the command /help is issued
    '''
    help_text = 'This bot is an example of OpenAI ChatGPT API usage. Have fun! To delete your chat history, use /delete command. You can also send voice messages.'
    await update.message.reply_text(help_text)

async def statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message with statistics when the command /statistics is issued
    '''
    # check if user is in whitelist
    access = await check_user(update, update.message.text, check_rate=False)
    # if not, return None
    if access != True:
        return None
    # if yes, send statistics
    stats_text = gpt.get_stats(id=update.effective_user.id)
    if stats_text is None or stats_text == '':
        stats_text = "Sorry, there is no statistics yet or something went wrong. Please try again later."
        logger.error('Could not get statistics for user: ' + str(update.effective_user.id))
    await update.message.reply_text(stats_text)

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Delete chat history when the command /delete is issued
    '''
    # check if user is in whitelist
    access = await check_user(update, update.message.text, check_rate=False)
    # if not, return None
    if access != True:
        return None
    # if yes, delete chat history
    success = gpt.delete_chat(update.effective_user.id)
    # send message about result
    if success:
        await update.message.reply_text("Chat history deleted")
    else:
        await update.message.reply_text("Sorry, it seems like there is no history with you. Please try again later.")
        logger.info('Could not delete chat history for user: ' + str(update.effective_user.id))

async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Check user rate limit when the command /limit is issued
    '''
    # check if user is in whitelist
    access = await check_user(update, update.message.text, check_rate=False)
    # if not, return None
    if access != True:
        return None
    # if yes, sent user his rate limit
    user = update.effective_user
    text = ratelimiter(user.id, check=True)
    if text is None:
        text = 'Unlimited'
    await update.message.reply_text(text)

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Answer to user message
    '''
    global application
    # check if user is in whitelist
    access = await check_user(update, update.message.text)
    await application.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    # if not, return None
    if access != True:
        return None
    # if yes, get answer
    answer = gpt.chat(id=update.effective_user.id, message=update.message.text)
    # add stats
    gpt.add_stats(id=update.effective_user.id, messages_sent=1)
    # send message with a result
    if answer is None:
        answer = "Sorry, something went wrong. You can try later or /delete your session."
        logger.error('Could not get answer to message: ' + update.message.text)
    try:
        await update.message.reply_markdown(answer)
    except:
        print('Could not send message. Trying to escape characters for text:\n' + answer)
        await update.message.reply_markdown_v2(escaping(answer))

async def answer_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Answer to user voice message
    '''
    global application
    # check if user is in whitelist
    access = await check_user(update, update.message.text)
    await application.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    # if not, return None
    if access != True:
        return None
    # if yes, get answer
    voice_file = await application.bot.get_file(update.message.voice.file_id)
    voice_file_path = './data/voice/' + str(update.message.voice.file_id) + '.ogg'
    voice_message = await voice_file.download_to_drive(custom_path=voice_file_path)
    answer = gpt.chat_voice(id=update.effective_user.id, audio_file=voice_file_path)
    # add stats
    gpt.add_stats(id=update.effective_user.id, voice_messages_sent=1)
    try:
        os.remove(voice_file_path)
        logger.info('Audio file ' + voice_file_path + ' was deleted (original)')
    except Exception as e:
        logger.exception('Could not delete original audio file ' + voice_file_path)
    # send message with a result
    if answer is None:
        answer = "Sorry, something went wrong. You can try later or /delete your session."
        logger.error('Could not get answer to voice message for user: ' + str(update.effective_user.id))
    try:
        await update.message.reply_markdown(answer)
    except:
        print('Could not send message. Trying to escape characters for text:\n' + answer)
        await update.message.reply_markdown_v2(escaping(answer))

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
        logger.warning("Restricted access to: " + str(user))
        if message is not None:
            if check_code(message, user.id):
                # if yes, add user to whitelist and send welcome message
                await update.message.reply_text("You are now able to use this bot. Welcome!")
                # delete chat history
                success = gpt.delete_chat(update.effective_user.id)
                if not success:
                    logger.info('Could not delete chat history for user: ' + str(update.effective_user.id))
                # send welcome message
                answer = gpt.chat(id=user.id, message=rf"Hi! I'm {user.full_name}!")
                if answer is None:
                    answer = "Sorry, something went wrong. Please try again later."
                    logger.error('Could not get answer to start message: ' + update.message.text)
                await update.message.reply_text(answer)
                return None
        await update.message.reply_text(rf"Sorry, {user.full_name}, you don't have access to this bot.")
        return False
    else:
        # check if user rate is limited
        if check_rate:
            ratecheck = ratelimiter(user.id)
            if ratecheck == False:
                logger.info("Rate limited user: " + str(user))
                await update.message.reply_text("You are rate limited. You can check your limits with /limit")
                return False
        return True

async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Sends a message with buttons attached when the command /style is issued. The buttons are used to choose a style for a bot.
    '''
    user = update.effective_user
    # check if user is in whitelist
    access = await check_user(update)
    if access == True: 
        # read chat modes
        modes = chat_modes_read()
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
    else:
        logger.info("Restricted access to style choosing to: " + str(user))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Handles the callback query when a button is pressed.
    '''
    user = update.effective_user
    # check if user is in whitelist
    access = await check_user(update)
    if access == True:
        # read chat modes
        modes = chat_modes_read()
        if modes is None:
            await update.message.reply_text('Sorry, something went wrong. Please try again later.')
            return None

        # delete chat history
        query = update.callback_query
        # print(query)
        await query.answer()
        success = gpt.delete_chat(update.effective_user.id)
        if success:
            logger.info('Deleted chat history for user for changing style: ' + str(update.effective_user.id))
        
        if query.data == "default":
            answer = gpt.chat(id=user.id, message=rf"Hi, I'm {user.full_name}! Please introduce yourself.")
        else:
            answer = gpt.chat(id=user.id, message=rf"Hi, I'm {user.full_name}! Please introduce yourself.", style=modes[query.data]['SystemMessage'])
        logger.info('Changed style for user: ' + str(update.effective_user.id) + ' to ' + str(query.data))

        if answer is None:
            answer = "Sorry, something went wrong. Please try again later."
            logger.error('Could not get answer for user: ' + str(update.effective_user.id))
        await query.edit_message_text(text=answer)

async def save_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Saves the current chat session to a file.
    '''
    user = update.effective_user
    # check if user is in whitelist
    access = await check_user(update)
    if access == True:
        # save chat history
        success = gpt.save_session(update.effective_user.id)
        if success:
            await update.message.reply_text("Chat session saved.")
        else:
            await update.message.reply_text("Sorry, something went wrong. Please try again later.")

async def load_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Loads the chat session.
    '''
    user = update.effective_user
    # check if user is in whitelist
    access = await check_user(update)
    if access == True:
        # give user a choice of sessions
        sessions = gpt.stored_sessions(update.effective_user.id)
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

async def downloader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    access = await check_user(update)
    if access != True:
        return None

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
        text = fp.extract_text(new_file_path)
        tt = round(time.time()-tic)
        logger.info('Process time: ' + str(tt) + ' seconds')

        if text is None or '':
            await update.message.reply_text("Sorry, something went wrong. Could not extract text from the file.")
            return None
        
        # if not, return None
        if access != True:
            return None
        # if yes, get answer from GPT
        answer = gpt.filechat(id=update.effective_user.id, text=text)
        if answer is None:
            answer = "Sorry, something went wrong. Could not get answer from GPT."
            logger.error('Could not get answer for user: ' + str(update.effective_user.id))
        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Sorry, something went wrong while processing the file.")


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

    # application.add_handler(CommandHandler("save_session", save_session_command))
    # application.add_handler(CommandHandler("load_session", load_session_command))
    # application.add_handler(CommandHandler("delete_session", delete_session_command))

    application.add_handler(CommandHandler("style", style_command))
    application.add_handler(CallbackQueryHandler(button))

    # on non command i.e message - answer the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
    application.add_handler(MessageHandler(filters.VOICE, answer_voice))

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

