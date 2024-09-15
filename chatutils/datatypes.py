from typing import Dict, Any, Optional, Union

class Message:
    """
    Message
    Represents a message that is sent to the chatbot.
    
    Main attributes:
        - content: Optional[Union[str, list]] (optional)
            str: text content
            list: list of text content and image content
        - role: Optional[str] (default: None, possible values: 'assistant', 'user', 'system', 'tool')
        - content_type: str (default: 'text', possible values: 'text', 'image', 'tool')
        
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
        - copy: Message (returns a copy of the message)
        - to_dict: dict (returns a dictionary representation of the message)
    """
    
    content: Optional[Union[str, list]] = None
    role: Optional[str] = None
    content_type: str = 'text'
    tokens: Dict[str, int] = {'prompt': 0, 'completion': 0}
    model: Dict[str, Any] = {'name': None, 'prompt_price': 0, 'completion_price': 0}
    finish_reason: Optional[str] = None
    tool_id: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    moderated: Optional[bool] = None
    misc: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.tool_name is not None:
            return f"{self.tool_name}({self.tool_args})"
        return str(self.content) if self.content is not None else ""

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Message) and self.content == other.content and self.content_type == other.content_type
    
    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)
    
    def __hash__(self) -> int:
        return hash((self.content, self.content_type))
    
    def __len__(self) -> int:
        if isinstance(self.content, str):
            return len(self.content)
        elif isinstance(self.content, dict):
            return len(str(self.content))
        return 0
    
    def copy(self) -> 'Message':
        new_message = Message()
        new_message.content = self.content 
        new_message.role = self.role
        new_message.content_type = self.content_type
        new_message.tokens = self.tokens.copy()
        new_message.model = self.model.copy()
        new_message.finish_reason = self.finish_reason
        new_message.tool_id = self.tool_id
        new_message.tool_args = self.tool_args
        new_message.tool_name = self.tool_name
        new_message.moderated = self.moderated
        new_message.misc = self.misc
        new_message.error = self.error
        return new_message
    
    def to_dict(self, text_only: bool = False) -> Dict[str, Any]:
        converted: Dict[str, Any] = {
            'role': self.role,
            'content': self.content.to_dict(),
            'content_type': self.content_type,
            'tokens': self.tokens
        }
        if self.model["name"] is not None:
            converted['model'] = self.model
        if self.finish_reason is not None:
            converted['finish_reason'] = self.finish_reason
        if self.tool_id is not None:
            converted['tool_id'] = self.tool_id
        if self.tool_args is not None:
            converted['tool_args'] = self.tool_args
        if self.tool_name is not None:
            converted['tool_name'] = self.tool_name
        if self.moderated is not None:
            converted['moderated'] = self.moderated
        if self.misc is not None:
            converted['misc'] = self.misc
        if self.error is not None:
            converted['error'] = self.error
        return converted
