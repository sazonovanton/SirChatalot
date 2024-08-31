"""
Data types for chatbot

Currently, the following data types are supported:
- Message
- Function
"""

class Message:
    """
    Message
    Represents a message that is sent to the chatbot
    Main attributes:
        - content: str (necessary)
        - content_type: str (default: 'text', possible values: 'text', 'image', 'function')
    Additional attributes:
        - tokens: dict (default: {'input': 0, 'output': 0})
        - price: int (default: 0)
        - model: str (default: None)
        - finish_reason: str (default: None)

    Methods:
        - __str__: str (returns the content of the message)
        - __repr__: str (returns the content of the message)
        - __eq__: bool (checks if the content and content_type of two messages are equal)
        - __ne__: bool (checks if the content and content_type of two messages are not equal)
        - __hash__: int (returns the hash of the content and content_type of the message)
        - __len__: int (returns the length of the content of the message)
    """
    def __init__(self, content: str, content_type: str = 'text'):
        self.content = content
        self.content_type = content_type
        self.tokens = {
            'input': 0,
            'output': 0
        }
        self.price = 0
        self.model = None
        self.finish_reason = None
        self.streaming = False

    def __str__(self):
        return self.content
    
    def __repr__(self):
        return self.content
    
    def __eq__(self, other):
        return self.content == other.content and self.content_type == other.content_type
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __hash__(self):
        return hash((self.content, self.content_type))
    
    def __len__(self):
        return len(self.content)