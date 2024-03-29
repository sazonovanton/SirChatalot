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
                                    "description": "Text prompt for image generation"
                                },
                                "image_orientation": {
                                    "type": "string",
                                    "enum": ["landscape", "portrait"],
                                    "description": "Orientation of image, if not specified, square image is generated"
                                },
                                "image_style": {
                                    "type": "string",
                                    "enum": ["natural", "vivid"],
                                    "description": "Style of image, if not specified, vivid image is generated"
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