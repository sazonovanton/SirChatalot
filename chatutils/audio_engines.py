# Description: Audio Transcription Engines for SirChatalot

from chatutils.misc import setup_logging, read_config
config = read_config('./data/.config')
logger = setup_logging(logger_name='SirChatalot-AudioEngines', log_level=config.get('Logging', 'LogLevel', fallback='WARNING'))

import os
import configparser

class WhisperEngine:
    def __init__(self):
        '''
        Initialize OpenAI API for Whisper
        '''
        from openai import AsyncOpenAI
        import openai 
        self.openai = openai
        self.config = configparser.ConfigParser({
            "Engine": "whisper",
            "AudioModel": "whisper-1",
            "AudioModelPrice": 0,
            "AudioFormat": "wav",
            "TranscribeOnly": False,
        })
        self.config.read('./data/.config', encoding='utf-8')

        if "AudioTranscript" in self.config.sections():
            self.settings = self.load_audio_transcription_settings()
        else:
            self.settings = self.load_audio_transcription_settings(deprecated=True)
        if self.settings is None:
            raise Exception('Could not load audio transcription settings')

        # Check for API key first in AudioTranscript section, then in OpenAI section
        api_key = self.settings.get("APIKey")
        if not api_key:
            if self.config.has_section("OpenAI") and self.config.has_option("OpenAI", "SecretKey"):
                api_key = self.config.get("OpenAI", "SecretKey")
            else:
                raise Exception("No API key provided for audio transcription")

        # Check for alternative API base
        base_url = self.settings.get("APIBase")
        if not base_url and self.config.has_section("OpenAI"):
            if self.config.has_option("OpenAI", "APIBase"):
                base_url = self.config.get("OpenAI", "APIBase")
        
        if base_url and base_url.lower() in ['default', '', 'none', 'false']:
            base_url = None

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        print('Audio transcription via Whisper is enabled')
        print(f'-- Audio transcription is using the {self.settings["AudioModel"]} model.')
        if self.settings["AudioModelPrice"] > 0:
            print(f'-- Audio transcription cost is {self.settings["AudioModelPrice"]} per minute.')
        print('-- Learn more: https://platform.openai.com/docs/guides/speech-to-text\n')

    def load_audio_transcription_settings(self, deprecated=False):
        '''
        Load audio transcription settings from config file
        '''
        try:
            settings = {}
            if not deprecated:
                settings["Engine"] = self.config.get("AudioTranscript", "Engine")
                settings["AudioModel"] = self.config.get("AudioTranscript", "AudioModel")
                settings["AudioModelPrice"] = float(self.config.get("AudioTranscript", "AudioModelPrice"))
                settings["AudioFormat"] = self.config.get("AudioTranscript", "AudioFormat")
                settings["TranscribeOnly"] = self.config.getboolean("AudioTranscript", "TranscribeOnly")
                if self.config.has_option("AudioTranscript", "APIKey"):
                    settings["APIKey"] = self.config.get("AudioTranscript", "APIKey")
                if self.config.has_option("AudioTranscript", "APIBase"):
                    settings["APIBase"] = self.config.get("AudioTranscript", "APIBase")
            else:
                # OpenAI section
                settings["Engine"] = "whisper"
                settings["AudioModel"] = self.config.get("OpenAI", "WhisperModel", fallback="whisper-1")
                settings["AudioModelPrice"] = self.config.getfloat("OpenAI", "WhisperModelPrice", fallback=0)
                settings["AudioFormat"] = self.config.get("OpenAI", "AudioFormat", fallback="wav")
                settings["TranscribeOnly"] = self.config.getboolean("OpenAI", "TranscribeOnly", fallback=False)
                settings["APIKey"] = self.config.get("OpenAI", "SecretKey")
                if self.config.has_option("OpenAI", "APIBase"):
                    settings["APIBase"] = self.config.get("OpenAI", "APIBase")
            return settings
        except Exception as e:
            logger.error(f'Could not load audio transcription settings due to: {e}')
            return None

    async def convert_audio(self, audio_file):
        '''
        Convert audio file to the configured format
        Input file can be of any format supported by pydub
        '''
        try:
            from pydub import AudioSegment
            converted_file = audio_file + '.' + self.settings["AudioFormat"]
            audio = AudioSegment.from_file(audio_file)
            audio.export(converted_file, format=self.settings["AudioFormat"])
            return converted_file
        except Exception as e:
            logger.exception(f'Could not convert audio to {self.settings["AudioFormat"]}')
            return None

    async def transcribe(self, audio_file):
        '''
        Transcribe audio file using OpenAI Whisper API
        '''
        try:
            converted_file = await self.convert_audio(audio_file)
            if converted_file is None:
                return None
            
            logger.debug(f"Attempting to transcribe file: {converted_file}")
            logger.debug(f"Using API base URL: {self.client.base_url}")
            
            with open(converted_file, "rb") as audio:
                transcript = await self.client.audio.transcriptions.create(
                    model=self.settings["AudioModel"],
                    file=audio,
                )
            
            os.remove(converted_file)
            return transcript.text
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI RateLimitError: {e}')
            return 'Service is getting rate limited. Please try again later.'
        except Exception as e:
            logger.exception(f'Could not transcribe audio: {str(e)}')
            return None

def get_audio_engine(engine_name):
    if engine_name.lower() == "whisper":
        return WhisperEngine()
    else:
        raise ValueError(f"Unsupported audio engine: {engine_name}")
