"""
Error messages for chatbot
"""

class ErrorResponses:
    """
    A class containing error messages for the chatbot.
    """
    invalid_input = "I'm sorry, I didn't understand that. 🤔"
    style_initiation = "I'm sorry, I wasn't able to initiate a new style. 🖋️"
    function_calling_error = "I'm sorry, I wasn't able to execute the function. 🛠️"
    message_answer_error = "I'm sorry, I couldn't respond to your message. 📝\nPlease try again later or contact the administrator."
    image_generation_error = "I'm sorry, I wasn't able to generate the image. 🖼️"
    speech_to_text_na = "I'm sorry, speech-to-text conversion is not available. 🎤"
    speech_to_text_error = "I'm sorry, I wasn't able to convert speech to text. 🎤"
    no_history = "It seems I don't have any history of our conversation. 📜"
    no_statistics = "It seems there are no statistics or something went wrong. 📊"
    unsupported_file = "This file type is not supported. 📁"
    av_processing_error = "Sorry, there was an error processing your audio/video file. 🎵"
    image_processing_error = "Sorry, something went wrong with image processing. 🖼️"

    general_error = "I'm sorry, something went wrong. 🤖\nPlease try again later or contact the administrator."
    general_error_wdelete = "I'm sorry, something went wrong. 🤖\nYou can try again later or /delete your session."

    @staticmethod
    def get_error_for_message(message):
        """
        Returns an error message for a given message.
        """
        return message
    
class GeneralResponses:
    """
    A class containing general responses for the chatbot.
    """
    drop_history = "Chat history has been deleted. 📜"
    unlimited = "Unlimited. 🌌"
    rate_limited = "You are rate limited. You can check your limits with /limit. 🕒"
    welcome = "You are now able to use this bot. Enjoy! 🤖"
    image_received = "Image received. I'll wait for your text before responding to it. 🖼️"
    banned = "You are banned. 🚫"
    vision_not_supported = "Sorry, working with images is not supported. 🖼️"
    image_generation_not_supported = "Sorry, image generation is not supported. 🖼️"

    @staticmethod
    def no_access(user):
        """
        Returns a message for a user that has no access to the chatbot.
        """
        return f"Sorry, {user}. You don't have access to this chatbot. 🚫"
    
    @staticmethod
    def rate_limit_exceeded(messages_count, limit, ratelimit_time):
        """
        Returns a message for a user that has exceeded the rate limit.
        """
        return f"You have reached your limit of {messages_count}/{limit} messages per {ratelimit_time} seconds. 🕒"
    
    @staticmethod
    def rate_limit_exceeded_simple(limit, ratelimit_time):
        """
        Returns a simple message for a user that has exceeded the rate limit.
        """
        return f"Rate limit of {limit} messages per {ratelimit_time} seconds exceeded. 🕒\nPlease wait."
    
# TESTING
if __name__ == "__main__":
    from responses import ErrorResponses as er
    
    print(er.get_error_for_message('test'))
