'''generate_image tool: create an image with the configured image engine.'''

import base64

from sirchatalot.tools import ToolContext, ToolResult, registry

SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'generate_image',
        'description': 'Generate image from text prompt',
        'parameters': {
            'type': 'object',
            'properties': {
                'prompt': {
                    'type': 'string',
                    'description': 'Text prompt for image generation (in english)',
                },
                'image_orientation': {
                    'type': 'string',
                    'enum': ['landscape', 'portrait'],
                    'description': 'Orientation of image, square if not specified',
                },
                'image_style': {
                    'type': 'string',
                    'enum': ['natural', 'vivid'],
                    'description': 'Style of image, vivid if not specified',
                },
            },
            'required': ['prompt'],
        },
    },
}


@registry.register(SCHEMA, requires='image_engine')
async def generate_image(ctx: ToolContext, prompt: str,
                         image_orientation: str | None = None,
                         image_style: str | None = None) -> ToolResult:
    b64_image, revised_prompt = await ctx.image_engine.generate_image(
        prompt, image_orientation=image_orientation, image_style=image_style,
        user_id=ctx.user_id,
    )
    if b64_image is None:
        return ToolResult(for_model=f'Image was not generated. {revised_prompt or ""}'.strip())
    return ToolResult(
        for_model=f'Image was generated and sent to the user '
                  f'(revised prompt: {revised_prompt or prompt})',
        images=[base64.b64decode(b64_image)],
    )
