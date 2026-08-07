'''
Central configuration for SirChatalot.

The whole application is configured by a single YAML file (default: ./data/config.yaml,
override with the SIRCHATALOT_CONFIG environment variable). This module is the only
place that reads it; everything else receives typed config objects via constructors.
'''

import os
import sys

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

DEFAULT_CONFIG_PATH = './data/config.yaml'


class ConfigError(Exception):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TelegramNetworkConfig(StrictModel):
    '''
    Bot API connectivity. The python-telegram-bot defaults (5 second timeouts,
    a single getUpdates connection with a 1 second pool timeout) assume a direct
    connection; behind a proxy they turn every hiccup into TimedOut/PoolTimeout,
    so everything here is deliberately more patient.
    '''
    connect_timeout: float = Field(default=20.0, gt=0)
    read_timeout: float = Field(default=30.0, gt=0)
    write_timeout: float = Field(default=30.0, gt=0)
    pool_timeout: float = Field(default=20.0, gt=0)
    connection_pool_size: int = Field(default=256, ge=1)
    get_updates_pool_size: int = Field(default=8, ge=1)
    poll_interval: float = Field(default=1.0, ge=0)   # pause between getUpdates calls
    poll_timeout: float = Field(default=30.0, gt=0)   # long polling timeout
    # how often the bot pings the API and refreshes the heartbeat file
    heartbeat_seconds: float = Field(default=60.0, gt=0)
    # reconnect from scratch after the API has been unreachable this long (0 = never)
    watchdog_seconds: float = Field(default=900.0, ge=0)

    @model_validator(mode='after')
    def _watchdog_above_heartbeat(self):
        if self.watchdog_seconds and self.watchdog_seconds < self.heartbeat_seconds:
            raise ValueError('telegram.network.watchdog_seconds must be 0 or '
                             '>= heartbeat_seconds')
        return self


class TelegramConfig(StrictModel):
    token: str
    access_codes: list[str] = []
    banlist_enabled: bool = False
    reply_to_message: bool = False
    admin_id: int | None = None   # gets error notifications when set
    network: TelegramNetworkConfig = TelegramNetworkConfig()


class RateLimitConfig(StrictModel):
    window_seconds: int = Field(gt=0)
    general_limit: int | None = Field(default=None, ge=0)
    # per-user overrides; 0 means unlimited
    user_overrides: dict[int, int] = {}


class ModelSpec(StrictModel):
    name: str
    model: str
    api_key: str = 'not-needed'  # keyless endpoints (Ollama, local vLLM) can omit this
    base_url: str | None = None
    # USD per 1M tokens
    prompt_price: float = 0.0
    completion_price: float = 0.0
    max_history_tokens: int = Field(default=16000, gt=0)
    temperature: float = 0.7
    vision: bool = False
    tools: bool = False
    timeout_seconds: float = Field(default=120.0, gt=0)
    proxy: str | None = None


class ChatConfig(StrictModel):
    system_message: str = (
        'You are a helpful assistant named Sir Chat-a-lot, '
        'who answers in a style of a knight in the middle ages.'
    )
    # smart history compaction: when the history exceeds compact_threshold of the
    # model's max_history_tokens, older messages are folded into a rolling summary
    # and only the last keep_recent_messages stay verbatim. false = plain trimming.
    summarize_too_long: bool = True
    compact_threshold: float = Field(default=0.75, gt=0.0, le=1.0)
    keep_recent_messages: int = Field(default=8, ge=2)
    moderation: bool = False
    image_size: int = Field(default=512, gt=0)
    end_user_id: bool = True
    max_session_length: int | None = Field(default=None, gt=0)


class StyleConfig(StrictModel):
    description: str
    system_message: str


class ImageRateLimit(StrictModel):
    count: int = Field(gt=0)
    window_seconds: int = Field(gt=0)


class ImageGenConfig(StrictModel):
    api_key: str = 'not-needed'  # keyless endpoints (Ollama, local vLLM) can omit this
    base_url: str | None = None
    model: str = 'dall-e-3'
    # 'images' = the OpenAI images endpoint (/v1/images/generations: OpenAI, xAI,
    # Together...). 'chat' = image generation through chat completions with
    # modalities (OpenRouter image models like google/gemini-2.5-flash-image).
    api: str = 'images'
    base_price: float = 0.0
    size: str = '1024x1024'
    style: str = 'vivid'
    quality: str = 'standard'
    rate_limit: ImageRateLimit | None = None

    @field_validator('api')
    @classmethod
    def _known_api(cls, v):
        if v not in ('images', 'chat'):
            raise ValueError(f'image_generation.api must be "images" or "chat", got: {v}')
        return v


class AudioConfig(StrictModel):
    api_key: str = 'not-needed'  # keyless endpoints (Ollama, local vLLM) can omit this
    base_url: str | None = None
    model: str = 'whisper-1'
    # 'transcriptions' = the OpenAI audio endpoint (/v1/audio/transcriptions).
    # 'chat' = transcription by a multimodal model via chat completions with
    # input_audio (OpenRouter models like google/gemini-2.5-flash).
    api: str = 'transcriptions'
    price_per_minute: float = 0.0
    format: str = 'mp3'
    transcribe_only: bool = False

    @field_validator('api')
    @classmethod
    def _known_api(cls, v):
        if v not in ('transcriptions', 'chat'):
            raise ValueError(f'audio.api must be "transcriptions" or "chat", got: {v}')
        return v

    @model_validator(mode='after')
    def _chat_format(self):
        if self.api == 'chat' and self.format not in ('wav', 'mp3'):
            raise ValueError('audio.api: chat requires format wav or mp3 (input_audio)')
        return self


class WebSearchConfig(StrictModel):
    provider: str = 'google'          # google | searxng | tavily | brave
    api_key: str | None = None        # google, tavily, brave
    cse_id: str | None = None         # google
    url: str | None = None            # searxng instance base URL
    results: int = Field(default=5, ge=1, le=10)

    @field_validator('provider')
    @classmethod
    def _known_provider(cls, v):
        if v.lower() not in ('google', 'searxng', 'tavily', 'brave'):
            raise ValueError(f'unknown web search provider: {v}')
        return v.lower()

    @model_validator(mode='after')
    def _provider_requirements(self):
        if self.provider == 'google' and not (self.api_key and self.cse_id):
            raise ValueError('google search requires api_key and cse_id')
        if self.provider == 'searxng' and not self.url:
            raise ValueError('searxng search requires url (instance base URL)')
        if self.provider in ('tavily', 'brave') and not self.api_key:
            raise ValueError(f'{self.provider} search requires api_key')
        return self


class UrlOpenConfig(StrictModel):
    enabled: bool = True
    summarize: bool = False
    trim_length: int | None = Field(default=3000, gt=0)
    # fetch pages through the Jina Reader (r.jina.ai) — returns clean markdown;
    # falls back to direct fetching when Jina fails
    via_jina: bool = True
    jina_api_key: str | None = None


class WebConfig(StrictModel):
    search: WebSearchConfig | None = None
    url_open: UrlOpenConfig | None = None


class EmbeddingsConfig(StrictModel):
    # 'openai' = any OpenAI-compatible embeddings API; 'local' = the ONNX
    # MiniLM model bundled with ChromaDB — no API calls at all
    provider: str = 'openai'
    api_key: str = 'not-needed'  # keyless endpoints (Ollama, local vLLM) can omit this
    base_url: str | None = None
    model: str = 'text-embedding-3-small'

    @field_validator('provider')
    @classmethod
    def _known_provider(cls, v):
        if v not in ('openai', 'local'):
            raise ValueError(f'embeddings.provider must be "openai" or "local", got: {v}')
        return v


class FilesConfig(StrictModel):
    embeddings: EmbeddingsConfig
    max_file_size_mb: int = Field(default=20, gt=0, le=20)
    chunk_size: int = Field(default=600, gt=0)
    overlap_percent: float = Field(default=0.1, ge=0.0, lt=1.0)
    max_distance: float = Field(default=1.0, gt=0)
    search_results: int = Field(default=4, ge=1)


class ProxiesConfig(StrictModel):
    '''HTTP(S) proxy URLs per traffic kind (e.g. http://user:pass@host:3128).'''
    telegram: str | None = None   # Bot API traffic
    llm: str | None = None        # all OpenAI-compatible calls (chat, images,
                                  # audio, embeddings); ModelSpec.proxy overrides per model
    search: str | None = None     # web search providers
    jina: str | None = None       # URL opening: Jina Reader and the direct fallback


class AgentConfig(StrictModel):
    max_iterations: int = Field(default=5, ge=1)
    # hard token budget per turn (prompt+completion across all iterations);
    # when exceeded the agent is forced to give a final answer. None = no budget
    max_turn_tokens: int | None = Field(default=None, gt=0)
    # tool results from PREVIOUS turns are truncated to this many characters
    # in the stored history (the model sees full results within the turn).
    # 0 = never truncate
    tool_result_keep_chars: int = Field(default=300, ge=0)


class MemoryConfig(StrictModel):
    max_items: int = Field(default=30, ge=1)


class McpServerConfig(StrictModel):
    name: str
    # stdio transport
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    # streamable-http transport
    url: str | None = None
    headers: dict[str, str] = {}
    timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator('name')
    @classmethod
    def _name_is_identifier(cls, v):
        if not v.replace('-', '_').isidentifier():
            raise ValueError(f'MCP server name must be a simple identifier, got: {v}')
        return v

    @model_validator(mode='after')
    def _one_transport(self):
        if bool(self.command) == bool(self.url):
            raise ValueError('MCP server needs exactly one of `command` (stdio) or `url` (http)')
        return self


class LoggingConfig(StrictModel):
    level: str = 'WARNING'
    log_chats: bool = False

    @field_validator('level')
    @classmethod
    def _valid_level(cls, v):
        if v.upper() not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
            raise ValueError(f'unknown logging level: {v}')
        return v.upper()


class AppConfig(StrictModel):
    telegram: TelegramConfig
    models: list[ModelSpec] = Field(min_length=1)
    default_model: str
    fallback_chain: list[str] = []
    chat: ChatConfig = ChatConfig()
    styles: dict[str, StyleConfig] = {}
    rate_limit: RateLimitConfig | None = None
    image_generation: ImageGenConfig | None = None
    audio: AudioConfig | None = None
    web: WebConfig | None = None
    files: FilesConfig | None = None
    memory: MemoryConfig | None = None
    mcp_servers: list[McpServerConfig] = []
    proxies: ProxiesConfig = ProxiesConfig()
    agent: AgentConfig = AgentConfig()
    logging: LoggingConfig = LoggingConfig()

    @model_validator(mode='after')
    def _check_model_names(self):
        names = [m.name for m in self.models]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f'duplicate model names: {", ".join(sorted(dupes))}')
        if self.default_model not in names:
            raise ValueError(f'default_model "{self.default_model}" is not defined in models')
        for name in self.fallback_chain:
            if name not in names:
                raise ValueError(f'fallback_chain entry "{name}" is not defined in models')
        server_names = [s.name for s in self.mcp_servers]
        if len(server_names) != len(set(server_names)):
            raise ValueError('duplicate MCP server names')
        return self

    def model_spec(self, name: str) -> ModelSpec | None:
        for spec in self.models:
            if spec.name == name:
                return spec
        return None


def config_path() -> str:
    return os.environ.get('SIRCHATALOT_CONFIG', DEFAULT_CONFIG_PATH)


def load_config(path: str | None = None) -> AppConfig:
    path = path or config_path()
    try:
        with open(path, encoding='utf-8') as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(
            f'Config file not found: {path}\n'
            f'Copy config.yaml.example to {DEFAULT_CONFIG_PATH} and fill in your keys.'
        ) from None
    except yaml.YAMLError as e:
        raise ConfigError(f'Config file {path} is not valid YAML:\n{e}') from None
    if not isinstance(raw, dict):
        raise ConfigError(f'Config file {path} must contain a YAML mapping, got {type(raw).__name__}')
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as e:
        lines = [f'Config file {path} is invalid:']
        for err in e.errors():
            loc = '.'.join(str(p) for p in err['loc']) or '<root>'
            lines.append(f'  - {loc}: {err["msg"]}')
        raise ConfigError('\n'.join(lines)) from None


def main() -> int:
    '''Validate the config file and print a short summary (python -m sirchatalot.config [path]).'''
    path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        cfg = load_config(path)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 1
    print(f'Config OK: {path or config_path()}')
    print(f'  models: {", ".join(m.name for m in cfg.models)} (default: {cfg.default_model})')
    print(f'  fallback chain: {cfg.fallback_chain or "none"}')
    for feature in ('rate_limit', 'image_generation', 'audio', 'web', 'files', 'memory'):
        state = 'enabled' if getattr(cfg, feature) is not None else 'disabled'
        print(f'  {feature}: {state}')
    print(f'  mcp servers: {", ".join(s.name for s in cfg.mcp_servers) or "none"}')
    print(f'  styles: {", ".join(cfg.styles) or "none"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
