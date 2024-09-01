"""
Error messages for chatbot
"""

class ErrorResponses:
    """
    Represents a class that contains error messages for the chatbot
    """
    def __init__(self):
        self.invalid_input = "I'm sorry, I didn't understand that. Please try again."

        self.style_initiation = "I'm sorry, I wasn't able to initiate new style 🖋️"

    def get_error_for_message(self, message):
        """
        Returns an error message for a given message
        """
        return message