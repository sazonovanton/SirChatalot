#!/bin/bash

# Check if python3 version is 3.6+
python_version=$(python3 -c "import sys; print(sys.version_info >= (3, 7))")

if [ "$python_version" != "True" ]; then
    echo "Error: Python version 3.7 or higher is required.."
    exit 1
else
    echo "$(python3 -V)"
fi

# Check if pip is installed
if ! command -v pip3 >/dev/null; then
    echo "Error: pip3 is not installed or not in PATH."
    exit 1
fi

# Install dependencies and check if it was successful
pip3 install -r requirements.txt > ./logs/pip.log
if [ $? -eq 0 ]; then
    echo "Dependencies (requirements.txt) have been installed."
else
    echo "Error: Failed to install dependencies (requirements.txt)."
    exit 1
fi

# Check if ffmpeg is installed
if ! command -v ffmpeg >/dev/null; then
    echo "Error: ffmpeg is not installed or not in PATH. Voice messages will not work."
    exit 1
else
    echo "$(ffmpeg -version | head -n 1)"
fi

# Check if ./data/.config exists
if [ ! -f ./data/.config ]; then
    echo "Error: './data/.config' does not exist. You can always create it using './data/config.example'."
    echo "Attempting to create './data/.config'... Press Enter to choose default values."

    # creating ./data/.config according to the default config above with user input
    echo "[Telegram]" > ./data/.config
    # ask for Token
    echo "Please enter your Telegram bot token:"
    read token
    # ask again if no token was entered
    while [ -z "$token" ]; do
        echo "Please enter your Telegram bot token:"
        read token
    done
    echo "Token = " $token >> ./data/.config
    # ask for AccessCodes, if no were entered, use default
    echo "Please enter your Telegram bot access codes (separated by commas) [Default: whitelistcode]:"
    read accesscodes
    if [ -z "$accesscodes" ]; then
        echo "AccessCodes = whitelistcode" >> ./data/.config
    else
        echo "AccessCodes = " $accesscodes >> ./data/.config
    fi
    echo "" >> ./data/.config
    echo "[OpenAI]" >> ./data/.config
    # ask for SecretKey
    echo "Please enter your OpenAI secret key:"
    read secretkey
    # ask again if no secret key was entered
    while [ -z "$secretkey" ]; do
        echo "Please enter your OpenAI secret key:"
        read secretkey
    done
    # ask for ChatModel, if no were entered, use default
    echo "Please enter OpenAI chat model to use [Default: gpt-3.5-turbo]:"
    read chatmodel
    if [ -z "$chatmodel" ]; then
        echo "ChatModel = gpt-3.5-turbo" >> ./data/.config
    else
        echo "ChatModel = " $chatmodel >> ./data/.config
    fi
    # ask for ChatModelPrice, if no were entered, use default
    echo "Please enter OpenAI chat model price [Default: 0.002]:"
    read chatmodelprice
    if [ -z "$chatmodelprice" ]; then
        echo "ChatModelPrice = 0.002" >> ./data/.config
    else
        echo "ChatModelPrice = " $chatmodelprice >> ./data/.config
    fi
    # ask for WhisperModel, if no were entered, use default
    echo "Please enter your OpenAI whisper model to use [Default: whisper-1]:"
    read whispermodel
    if [ -z "$whispermodel" ]; then
        echo "WhisperModel = whisper-1" >> ./data/.config
    else
        echo "WhisperModel = " $whispermodel >> ./data/.config
    fi
    # ask for WhisperModelPrice, if no were entered, use default
    echo "Please enter OpenAI whisper model price [Default: 0.006]:"
    read whispermodelprice
    if [ -z "$whispermodelprice" ]; then
        echo "WhisperModelPrice = 0.006" >> ./data/.config
    else
        echo "WhisperModelPrice = " $whispermodelprice >> ./data/.config
    fi
    # ask for Temperature, if no were entered, use default
    echo "Please enter OpenAI chat model temperature [Default: 0.7]:"
    read temperature
    if [ -z "$temperature" ]; then
        echo "Temperature = 0.7" >> ./data/.config
    else
        echo "Temperature = " $temperature >> ./data/.config
    fi
    # ask for MaxTokens, if no were entered, use default
    echo "Please enter max tokens for OpenAI chat model [Default: 1000]:"
    read maxtokens
    if [ -z "$maxtokens" ]; then
        echo "MaxTokens = 1000" >> ./data/.config
    else
        echo "MaxTokens = " $maxtokens >> ./data/.config
    fi
    # ask for AudioFormat, if no were entered, use default
    echo "Please enter audio format for OpenAI whisper model [Default: wav]:"
    read audioformat
    if [ -z "$audioformat" ]; then
        echo "AudioFormat = wav" >> ./data/.config
    else
        echo "AudioFormat = " $audioformat >> ./data/.config
    fi
    # Do not ask for SystemMessage, use default
    echo "SystemMessage = You are a helpful assistant named Sir Chat-a-lot, who answers in a style of a knight in the middle ages." >> ./data/.config
    echo "" 
    echo "Created './data/.config' file with this content:"
    cat ./data/.config
    echo ""
    echo "You can always edit it later in './data/.config'."
else
    echo "Config file exists: './data/.config'"
fi

# new line
echo ""

echo "Starting bot..."
echo "Logs are stored in './logs/common.log'..."

# new line
echo ""

# Launch main.py and redirect output to a file
python3 main.py 