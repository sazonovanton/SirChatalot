"""
Error messages for chatbot
"""

class ErrorResponses:
    """
    Represents a class that contains error messages for the chatbot
    """
    invalid_input = "I'm sorry, I didn't understand that 🤔"
    style_initiation = "I'm sorry, I wasn't able to initiate new style 🖋️"
    function_calling_error = "I'm sorry, I wasn't able to call the function 📞"
    message_answer_error = "I'm sorry, I wasn't able to answer the message 📝\nTry again later or contact admin."
    image_generation_error = "I'm sorry, I wasn't able to generate the image 🖼️"
    speech_to_text_na = "I'm sorry, speech to text conversion is not available 🎤"
    speech_to_text_error = "I'm sorry, I wasn't able to convert speech to text 🎤"
    no_history = "It seems like I don't have any history of our conversation 📜"
    no_statistics = "It seems like there are no statistics yet or something went wrong 📊"
    unsupported_file = "This file type is not supported 📁"
    av_processing_error = "Sorry, there was an error processing your audio/video file 🎵"
    image_processing_error = "Sorry, something went wrong with image processing 🖼️"
    image_generation_error = "I'm sorry, I wasn't able to generate the image 🖼️"

    general_error = "I'm sorry, something went wrong 🤖\nTry again later or contact admin."
    general_error_wdelete = "I'm sorry, something went wrong 🤖\nYou can try later or /delete your session."

    def get_error_for_message(self, message):
        """
        Returns an error message for a given message
        """
        return message
    
class GeneralResponses:
    """
    Represents a class that contains general responses for the chatbot
    """
    drop_history = "Chat history has been deleted 📜"
    unlimited = "Unlimited 🌌"
    rate_limited = "You are rate limited. You can check your limits with /limit 🕒"
    welcome = "You are now able to use this bot. Enjoy! 🤖"
    image_recieved = "Image recieved. I'll wait for your text before answering to it 🖼️"
    banned = "You are banned 🚫"
    vision_not_supported = "Sorry, working with images is not supported 🖼️"
    image_generation_not_supported = "Sorry, image generation is not supported 🖼️"

    def no_access(self, user):
        """
        Returns a message for a user that has no access to the chatbot
        """
        return f"Sorry, {user}. You don't have access to this chatbot 🚫"
    
    def rate_limit_exceeded(self, messages_count, limit, ratelimit_time):
        """
        Returns a message for a user that has exceeded the rate limit
        """
        return f"You have used your limit of {messages_count}/{limit} messages per {ratelimit_time} seconds 🕒"

    def rate_limit_exceeded_simple(self, limit, ratelimit_time):
        """
        Returns a simple message for a user that has exceeded the rate limit
        """
        return f"Rate limit of {limit} messages per {ratelimit_time} seconds exceeded 🕒\nPlease wait."
