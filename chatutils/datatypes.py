"""
Data types for chatbot

Currently, the following data types are supported:
- Message
- FunctionResponse
"""
    
class Message:
    """
    Message
    Represents a message that is sent to the chatbot
    Main attributes:
        - content: str (necessary)
        - content_type: str (default: 'text', possible values: 'text', 'image', 'function')
    Additional attributes:
        - tokens: dict (default: {'prompt': 0, 'completion': 0})
        - price: int (default: 0)
        - model: dict (default: {'name': None, 'prompt_price': 0, 'completion_price': 0})
        - finish_reason: str (default: None)
        - moderated: bool (default: None)
    Methods:
        - __str__: str (returns the content of the message)
        - __eq__: bool (checks if the content and content_type of two messages are equal)
        - __ne__: bool (checks if the content and content_type of two messages are not equal)
        - __hash__: int (returns the hash of the content and content_type of the message)
        - __len__: int (returns the length of the content of the message)
        - to_dict: dict (returns a dictionary representation of the message)
    """
    def __init__(self):
        self.content = None
        self.role = None
        self.content_type = 'text'
        self.tokens = {
            'prompt': 0,
            'completion': 0
        }
        self.price = 0
        self.model = {
            'name': None,
            'prompt_price': 0,
            'completion_price': 0
        }
        self.finish_reason = None
        self.moderated = None
        self.misc = None
        self.error = None

    def __str__(self):
        return str(self.content)
    
    def __eq__(self, other):
        return self.content == other.content and self.content_type == other.content_type
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __hash__(self):
        return hash((self.content, self.content_type))
    
    def __len__(self):
        return len(self.content)
    
    def copy(self):
        new_message = Message()
        new_message.content = self.content
        new_message.role = self.role
        new_message.content_type = self.content_type
        new_message.tokens = self.tokens
        new_message.price = self.price
        new_message.model = self.model
        new_message.finish_reason = self.finish_reason
        new_message.moderated = self.moderated
        new_message.misc = self.misc
        new_message.error = self.error
        return new_message
    
    def to_dict(self):
        converted = {}
        converted['content'] = self.content
        converted['content_type'] = self.content_type
        converted['tokens'] = self.tokens
        converted['price'] = self.price
        if self.model["name"] is not None:
            converted['model'] = self.model
        if self.finish_reason is not None:
            converted['finish_reason'] = self.finish_reason
        if self.moderated is not None:
            converted['moderated'] = self.moderated
        if self.misc is not None:
            converted['misc'] = self.misc
        if self.error is not None:
            converted['error'] = self.error
        return converted
    
class FunctionResponse:
    """
    FunctionResponse
    Represents a function response 
    Main attributes:
        - function_name: str (necessary)
        - function_args: dict (default: None)
        - tool_id: str (default: None)
        - content: any (default: None) - added after the function is executed
    Additional attributes:
        - price: int (default: 0)
        - text: str (default: None)
        - misc: dict (default: None)

    Methods:
        - __str__: str (returns the function name and arguments)
        - __eq__: bool (checks if the function name and arguments of two function responses are equal)
        - __ne__: bool (checks if the function name and arguments of two function responses are not equal)
        - __hash__: int (returns the hash of the function name and arguments of the function response)
        - to_dict: dict (returns a dictionary representation of the function response)
    """
    def __init__(self):
        self.function_name = None
        self.function_args = None
        self.content = None
        self.tool_id = None
        self.price = 0
        self.image = None
        self.text = None
        self.misc = None
        self.error = None

    def __str__(self):
        return f"{self.function_name}({self.function_args})"
    
    def __eq__(self, other):
        return self.function_name == other.function_name and self.function_args == other.function_args 
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __hash__(self):
        return hash((self.function_name, self.function_args))
    
    def copy(self):
        new_response = FunctionResponse()
        new_response.function_name = self.function_name
        new_response.function_args = self.function_args
        new_response.content = self.content
        new_response.tool_id = self.tool_id
        new_response.price = self.price
        new_response.image = self.image
        new_response.text = self.text
        new_response.misc = self.misc
        new_response.error = self.error
        return new_response

    def to_dict(self):
        converted = {}
        converted['function_name'] = self.function_name
        if self.function_args is not None:
            converted['function_args'] = self.function_args
        if self.tool_id is not None:
            converted['tool_id'] = self.tool_id
        if self.content is not None:
            converted['content'] = self.content
        converted['price'] = self.price
        if self.image is not None:
            converted['image'] = self.image
        if self.text is not None:
            converted['text'] = self.text
        if self.error is not None:
            converted['error'] = self.error
        if self.misc is not None:
            converted['misc'] = self.misc
        return converted