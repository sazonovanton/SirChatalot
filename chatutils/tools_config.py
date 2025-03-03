# Document with configs for tools calling.

class OpenAIConfig:
    image_generation = {   
                    "type": "function",
                    "function": {
                        "name": "generate_image",
                        "description": "Generate image from text prompt",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "prompt": {
                                    "type": "string",
                                    "description": "Text prompt for image generation (in english)"
                                },
                                "image_orientation": {
                                    "type": "string",
                                    "enum": ["landscape", "portrait"],
                                    "description": "Orientation of image, if not specified, square image is generated (preferably)"
                                },
                                "image_style": {
                                    "type": "string",
                                    "enum": ["natural", "vivid"],
                                    "description": "Style of image, if not specified, vivid image is generated (preferably)"
                                }
                            },
                            "required": ["prompt"],
                        }
                    }
                }
    
    web_search = {
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "description": "Search the web using Search Engine API",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Query for web search"
                                    }
                                },
                                "required": ["query"],
                            }
                        }
                    }
    
    url_opener = {
                        "type": "function",
                        "function": {
                            "name": "url_opener",
                            "description": "Open URL and get the content",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "url": {
                                        "type": "string",
                                        "description": "URL to open"
                                    }
                                },
                                "required": ["url"],
                            }
                        }
                    }
    
    semantic_search = {
                        "type": "function",
                        "function": {
                            "name": "semantic_search",
                            "description": "Searches for similar text chunks in RAG database using given text. Returns top similar text chunks. Should be used to find information in internal documents.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "text": {
                                        "type": "string",
                                        "description": "Text to search similar text chunks for"
                                    },
                                    "n_results": {
                                        "type": "integer",
                                        "description": "Number of results to return",
                                        "default": 3
                                    }
                                },
                                "required": ["text"],  
                            }
                        }
                    }

class AnthropicConfig:
    """Rewrite the OpenAIConfig class to AnthropicConfig class"""
    def __init__(self) -> None:
        # extract the function from OpenAIConfig
        self.image_generation = OpenAIConfig.image_generation['function']
        self.web_search = OpenAIConfig.web_search['function']
        self.url_opener = OpenAIConfig.url_opener['function']
        self.semantic_search = OpenAIConfig.semantic_search['function']

        # rename parameters to input_schema
        self.image_generation['input_schema'] = self.image_generation.pop('parameters')
        self.web_search['input_schema'] = self.web_search.pop('parameters')
        self.url_opener['input_schema'] = self.url_opener.pop('parameters')
        self.semantic_search['input_schema'] = self.semantic_search.pop('parameters')
