"""
Miscellaneous utility functions.
"""
import os
import logging
import logging.handlers
import configparser

def setup_logging(log_file: str = './logs/sirchatalot.log', 
                  logger_name: str = 'SirChatalot-Logger',
                  log_level: str = 'WARNING', 
                  interval: int = 1,
                  backup_count: int = 5):
    """
    Set up logging to log to a file.
    Rotate log files when they reach max_kb size and keep backup_count files .
    Input:
        log_file: str, path to log file, default './logs/sirchatalot.log'
        logger_name: str, name of logger, default 'SirChatalot-Logger'
        log_level: str, log level, default 'WARNING'
        interval: int, interval of log rotation, default 1
        backup_count: int, number of backup files to keep, default 5
    Output:
        logger: logging.Logger object
    """
    # create log folder if not exist
    log_folder = os.path.dirname(log_file)
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    handler = logging.handlers.TimedRotatingFileHandler(log_file, 
                                                        when='D', 
                                                        interval=interval, 
                                                        backupCount=backup_count,
                                                        encoding='utf-8')
    formatter = logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, log_level, 'WARNING'))
    logger.addHandler(handler)
    return logger

def read_config(config_file: str = './data/.config'):
    """
    Read configuration from a config file.
    Input:
        config_file: str, path to config file, default './data/.config'
    Output:
        config: dict, configuration parameters
    """
    config = configparser.ConfigParser()
    config.read(config_file,
                encoding='utf-8')
    return config
    
async def leave_only_text(message, logger=None):
    '''
    Leave only text in message with images
    '''
    if message is None:
        return None, False
    try:
        message_copy = message.copy()
        trimmed = False

        if message_copy.content_type == 'image' and type(message_copy.content) == list:
            for i in range(len(message_copy.content)):
                if message_copy.content[i]['type'] == 'text':
                    message_copy.content = message_copy.content[i]['text']
                    trimmed = True
                    break
        return message_copy, trimmed
    except Exception as e:
        if logger:
            logger.error(f'Could not leave only text in message: {e}')
        else:
            raise f'Could not leave only text in message: {e}'
        return message, False
