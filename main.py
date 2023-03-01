# Description: Main file for SirChatalot bot

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
accesscodes = config.get("Telegram", "AccessCodes").split(',')
accesscodes = [x.strip() for x in accesscodes]

from gptproc import GPT
gpt = GPT()

# main libraries
import asyncio
import sys
import os
import time
from telegram import ForceReply, Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import codecs

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message when the command /start is issued.
    '''
    user = update.effective_user
    access = await check_user(update, update.message.text)
    if access:
        answer = gpt.chat(id=user.id, message=rf"Hi! I'm {user.full_name}!")
        if answer is None:
            answer = "Sorry, something went wrong. Please try again later."
            logger.error('Could not get answer to start message: ' + update.message.text)
        else:
            await update.message.reply_html(answer)
    else:
        await update.message.reply_text(rf"Sorry, {user.full_name}, you are not allowed to use this bot.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Send a message when the command /help is issued
    '''
    help_text = 'This bot is an example of OpenAI ChatGPT API usage. Have fun! To delete your chat history, use /delete command.'
    await update.message.reply_text(help_text)

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Delete chat history when the command /delete is issued
    '''
    # check if user is in whitelist
    access = await check_user(update, update.message.text)
    # if not, return None
    if access != True:
        return None
    # if yes, delete chat history
    success = gpt.delete_chat(update.effective_user.id)
    # send message about result
    if success:
        await update.message.reply_text("Chat history deleted.")
    else:
        await update.message.reply_text("Could not delete chat history. Please try again later.")
        logger.error('Could not delete chat history for user: ' + str(update.effective_user.id))

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''
    Answer to user message
    '''
    # check if user is in whitelist
    access = await check_user(update, update.message.text)
    # if not, return None
    if access != True:
        return None
    # if yes, get answer
    answer = gpt.chat(id=update.effective_user.id, message=update.message.text)
    # send message with a result
    if answer is None:
        answer = "Sorry, something went wrong. Please try again later."
        logger.error('Could not get answer to message: ' + update.message.text)
    await update.message.reply_text(answer)

def check_code(code, user_id) -> bool:
    '''
    Check if code is in accesscodes
    '''
    # check if code is in accesscodes
    try:
        if code in accesscodes:
            # add user to whitelist if code is correct
            with codecs.open("./data/whitelist.txt", "a", "utf-8") as f:
                f.write(str(user_id))
            return True
    except:
        logger.exception('Could not add user to whitelist')
    return False

async def check_user(update, message=None) -> bool:
    '''
    Check if user is in whitelist
    '''
    # read whitelist
    try:
        with codecs.open("./data/whitelist.txt", "r", "utf-8") as f:
            # Read the contents of the file into a list
            lines = f.readlines()
        whitelist = [line.rstrip('\n') for line in lines]
    except:
        logger.exception('No whitelist')
        whitelist = []

    user = update.effective_user

    # check if user is in whitelist
    if str(user.id) not in whitelist:
        # if not, check if user sent access code
        logger.info("Restricted access to: " + str(user))
        if message is not None:
            if check_code(message, user.id):
                await update.message.reply_text("I whitelisted you.")
                answer = gpt.chat(id=user.id, message=rf"Hi! I'm {user.full_name}!")
                if answer is None:
                    answer = "Sorry, something went wrong. Please try again later."
                    logger.error('Could not get answer to start message: ' + update.message.text)
                await update.message.reply_text(answer)
                return True
        await update.message.reply_text("Sorry, you don't have access to this bot.")
        return False
    else:
        return True
   

def main() -> None:
    '''
    Start the bot.
    '''
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("delete", delete_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))

    # Run the bot until the Ctrl-C is pressed
    application.run_polling()


if __name__ == "__main__":
    main()

