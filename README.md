# SirChatalot

A Telegram bot that proves you don't need a body to have a personality.

The bot talks to any **OpenAI-compatible** chat API — OpenAI, OpenRouter, local models
(Ollama, vLLM), or Anthropic / YandexGPT via their OpenAI-compatible endpoints. You can
configure several models at once, switch between them from the chat with `/model`, and
define a fallback chain that is tried automatically when the primary model errors out.

## Features

* **Multiple models** — per-user runtime switching (`/model`) and an optional fallback chain.
* **Agentic tool use** — the model can generate images, search the web, open URLs,
  search and read your uploaded documents, across several tool-calling iterations per
  turn — with live status updates in the chat ("🔍 Searching the web…"), deduplication
  of repeated calls, and an optional per-turn token budget. Tool results from older
  turns are automatically shrunk in history to save tokens.
* **MCP servers** — declare [Model Context Protocol](https://modelcontextprotocol.io)
  servers (stdio or streamable-http) and their tools become available to the model.
* **Per-user tool control** — `/tools` lets every user enable/disable individual
  built-in tools and whole MCP servers.
* **User memory** — the model saves lasting facts about the user; they are injected
  into the system prompt. Users view and delete them with `/memory`.
* **Smart history compaction** — older history is folded into an incrementally updated
  rolling summary; recent turns stay verbatim.
* **Documents / agentic RAG** — send PDF, DOCX, PPTX, TXT and similar files; they are
  chunked, embedded and stored in ChromaDB, and the model searches them when answering.
* **Vision** — send photos to vision-capable models.
* **Voice/video messages** — Whisper (or compatible) transcription, with an optional
  transcript-only mode. Requires [ffmpeg](https://ffmpeg.org/).
* **Image generation** — `/imagine` or just ask the bot; OpenAI images API or
  OpenRouter chat-based image models.
* **Web search** — Google CSE, SearXNG, Tavily or Brave; page opening via the Jina
  Reader or fully local extraction (trafilatura), both LLM-friendly markdown.
* **Proper Telegram formatting** — model markdown is converted to valid MarkdownV2
  (code blocks, lists, quotes) with a plain-text fallback; the "typing…" indicator
  stays alive while generating.
* **`/retry` and `/undo`**, styles (`/style`), whitelisting via access codes, banlist,
  per-user rate limits, usage statistics with cost estimates.
* **Per-kind HTTP proxies** — separate proxies for Telegram, LLM calls, web search
  and page opening.

## Commands

| Command | Description |
|---|---|
| `/start` | Start the conversation |
| `/help` | Show help |
| `/retry` | Regenerate the answer to your last message |
| `/undo` | Remove the last exchange from the history |
| `/delete` | Delete the whole chat history |
| `/model` | Choose the AI model (per user) |
| `/style` | Choose a bot personality |
| `/tools` | Enable/disable AI tools and MCP servers (per user) |
| `/memory` | View and delete what the bot remembers about you |
| `/imagine <prompt>` | Generate an image |
| `/listfiles`, `/deletefiles` | Manage your uploaded documents |
| `/statistics` | Usage statistics and approximate cost |
| `/limit` | Check your rate limit |

The command menu is registered in Telegram automatically at startup.

## Getting started

1. Create a bot with [BotFather](https://t.me/botfather) and get the token.
2. Clone the repository and install dependencies: `pip install -r requirements.txt`
   (plus `ffmpeg` for voice support).
3. Copy `config.yaml.example` to `./data/config.yaml` and fill in your keys.
4. Validate the config: `python3 -m sirchatalot.config ./data/config.yaml`
5. Run `python3 main.py`, or use Docker: `docker compose up -d --build`.

## Configuration

Everything is configured by a single YAML file: `./data/config.yaml`
(`config.yaml.example` is a fully commented template; the path can be overridden
with the `SIRCHATALOT_CONFIG` environment variable). Unknown keys are rejected at
startup with a clear error, so typos can't silently disable features.

**Optional sections** — `rate_limit`, `image_generation`, `audio`, `web`, `files`,
`memory` — enable a feature by their presence: remove the section to disable it.

### telegram (required)

```yaml
telegram:
  token: "0000000000:xxxx"          # BotFather token
  access_codes: [somecode]          # remove/empty = the bot is open to everyone
  banlist_enabled: false            # ban users listed in ./data/banlist.txt
  reply_to_message: false           # reply directly to the user's message
  # admin_id: 123456789             # gets error notifications (throttled)
```

If `access_codes` is set, the bot answers only whitelisted users; sending a code
whitelists the sender (stored in `./data/whitelist.txt`, one id per line, editable
by hand).

Connectivity is configured under `telegram.network`. The defaults are tuned for a
proxied, unstable link (python-telegram-bot's own defaults — 5 second timeouts and
a single `getUpdates` connection with a 1 second pool timeout — produce endless
`TimedOut` / `Pool timeout` errors behind a proxy), so override only if you need to:

```yaml
telegram:
  network:
    connect_timeout: 20       # seconds
    read_timeout: 30
    write_timeout: 30
    pool_timeout: 20
    connection_pool_size: 256
    get_updates_pool_size: 8  # separate pool for long polling
    poll_interval: 1.0        # pause between getUpdates calls
    poll_timeout: 30          # long polling timeout
    heartbeat_seconds: 60     # API ping + heartbeat file for the healthcheck
    watchdog_seconds: 900     # reconnect after this long without the API (0 = off)
```

How the bot survives a flaky link:

- the initial connection is retried forever, so starting with the proxy down is fine;
- polling errors are retried by python-telegram-bot itself;
- every `heartbeat_seconds` the bot pings the Bot API and writes `./data/heartbeat`;
- after `watchdog_seconds` without a reachable API it rebuilds the connection from
  scratch (new HTTP clients), and if polling dies outright the process restarts it
  with a 5 → 120 second backoff.

### models, default_model, fallback_chain (required)

Any OpenAI-compatible endpoint works. Each entry:

```yaml
models:
  - name: gpt-4o-mini        # display name for /model — must be unique
    model: gpt-4o-mini       # model id sent to the API
    api_key: "sk-..."
    base_url: null           # null = api.openai.com; e.g. https://openrouter.ai/api/v1,
                             # http://localhost:11434/v1 (Ollama), ...
    prompt_price: 0.15       # USD per 1M tokens, used for /statistics only
    completion_price: 0.6
    max_history_tokens: 16000  # history budget before compaction/trimming
    temperature: 0.7
    vision: true             # the model accepts images
    tools: true              # the model supports tool calling
    timeout_seconds: 120
    proxy: null              # overrides proxies.llm for this model

default_model: gpt-4o-mini
fallback_chain: [claude-sonnet]  # tried in order on timeouts/rate limits/5xx;
                                 # 4xx errors (bad key, bad request) do not fall back
```

Users switch models with `/model`; the choice is stored per user. When the selected
model lacks `vision` or `tools`, the history is adapted automatically on send
(images become placeholders, tool messages are flattened to text) — nothing is lost
in the stored history. If a model is removed from the config, users who had it
selected silently revert to `default_model`.

### chat

```yaml
chat:
  system_message: "You are a helpful assistant..."
  summarize_too_long: true    # true = rolling-summary compaction, false = plain trimming
  compact_threshold: 0.75     # compact when history exceeds this fraction of
                              # the model's max_history_tokens
  keep_recent_messages: 8     # how many recent messages stay verbatim
  moderation: false           # OpenAI moderation API on user messages
                              # (requires the default model to be api.openai.com)
  image_size: 512             # long side for downscaling incoming photos
  end_user_id: true           # pass a hashed user id to the API (abuse tracing)
  # max_session_length: 15    # warn the user when the session gets this long
```

How compaction works: when the history exceeds `compact_threshold` of the model's
`max_history_tokens`, everything except the last `keep_recent_messages` messages is
summarized into a single rolling-summary message kept right after the system prompt.
On the next compaction the previous summary is fed back to the model and *updated*,
so long-lived facts survive. Tool call/result pairs are never split.

### styles

Bot personalities for `/style` (switching clears the current session):

```yaml
styles:
  Alice:
    description: Alice is empathetic and friendly
    system_message: You are an empathetic and friendly woman named Alice...
```

### memory (optional)

```yaml
memory:
  max_items: 30    # per user; oldest entries are evicted beyond this
```

Gives the model a `save_memory` tool and injects saved facts into the system prompt.
Users manage their memory with `/memory` (delete one / clear all).

### rate_limit (optional)

```yaml
rate_limit:
  window_seconds: 3600
  general_limit: 100        # messages per window; remove = unlimited
  user_overrides:           # per-user overrides, 0 = unlimited
    123456789: 500
```

Sliding window, exactly `general_limit` messages allowed per window.
`/statistics`, `/delete` and `/limit` don't consume the limit.

### image_generation (optional)

```yaml
image_generation:
  api_key: "sk-..."
  base_url: null
  model: dall-e-3
  api: images               # images | chat (see below)
  base_price: 0.04          # USD per image, for /statistics
  size: 1024x1024
  style: vivid              # dall-e only
  quality: standard         # dall-e only
  rate_limit: {count: 16, window_seconds: 3600}   # per user, optional
```

Two API modes:

* `api: images` — the OpenAI images endpoint (`/v1/images/generations`): OpenAI
  DALL-E / gpt-image-1, xAI, Together and other providers that implement it.
* `api: chat` — image generation through chat completions with modalities. This is
  how **OpenRouter** serves image models. The bot requests image+text output (so it
  can show the model's caption) and automatically retries with image-only for models
  that don't support the combination (e.g. FLUX variants):

  ```yaml
  image_generation:
    api: chat
    model: google/gemini-2.5-flash-image
    base_url: https://openrouter.ai/api/v1
    api_key: "sk-or-..."
  ```

`/imagine` prompt flags:
* images mode (DALL-E): `--natural`/`--vivid`, `--sd`/`--hd`,
  `--horizontal`/`--vertical`, `--revision` (show the revised prompt).
* chat mode (OpenRouter): `--ratio 16:9` (aspect ratio: 1:1, 16:9, 9:16, 4:3,
  3:4, 3:2, 2:3, 4:5, 5:4, 21:9, 9:21), `--res 512|1K|2K|4K`, and the
  `--horizontal`/`--vertical`/`--square` shortcuts. These map to OpenRouter's
  `image_config`; if a model rejects it the bot retries without it. Support
  depends on the model.

The model can also generate images by itself via the `generate_image` tool.

### audio (optional)

```yaml
audio:
  api_key: "sk-..."
  base_url: null
  model: whisper-1
  api: transcriptions       # transcriptions | chat (see below)
  price_per_minute: 0.006
  format: mp3               # what to convert Telegram audio into (needs ffmpeg);
                            # chat mode requires wav or mp3
  transcribe_only: false    # true = reply with the transcript, don't answer
```

Two API modes, mirroring image generation:

* `api: transcriptions` — the OpenAI audio endpoint (`/v1/audio/transcriptions`):
  Whisper, gpt-4o-transcribe or any compatible provider.
* `api: chat` — transcription by a multimodal model via chat completions with
  `input_audio`. This is the way to do it on **OpenRouter**:

  ```yaml
  audio:
    api: chat
    model: google/gemini-2.5-flash
    base_url: https://openrouter.ai/api/v1
    api_key: "sk-or-..."
    format: mp3
  ```

### web (optional)

```yaml
web:
  search:                   # remove to disable the web_search tool
    provider: searxng       # google | searxng | tavily | brave
    url: http://localhost:8080   # searxng: instance base URL
    # api_key: "..."        # google / tavily / brave
    # cse_id: "..."         # google only
    results: 5
  url_open:                 # remove to disable the url_opener tool
    enabled: true
    summarize: false        # summarize page content before giving it to the model
    trim_length: 3000       # max characters of page content
    via_jina: true          # fetch pages through r.jina.ai (clean markdown)
    # jina_api_key: "jina_..."  # optional, higher rate limits
```

Provider requirements: `google` — `api_key` + `cse_id`; `searxng` — `url` (your
instance, JSON API must be enabled); `tavily`/`brave` — `api_key`.

Page opening: with `via_jina: true` pages are fetched through the
[Jina Reader](https://jina.ai/reader) and arrive as clean markdown; on any Jina
failure the bot falls back to a direct fetch. With `via_jina: false` everything is
local: the page is downloaded directly and the main content is extracted with
trafilatura (markdown, boilerplate stripped). Direct fetches are SSRF-guarded:
http/https only, private/loopback/link-local addresses are rejected at DNS
resolution time, response size is capped.

### files — documents / RAG (optional)

```yaml
files:
  embeddings:
    provider: openai          # openai | local
    api_key: "sk-..."
    base_url: null
    model: text-embedding-3-small
  max_file_size_mb: 20      # Telegram bots can't download files over 20 MB anyway
  chunk_size: 600           # characters per chunk
  overlap_percent: 0.1
  max_distance: 1.0         # drop search hits farther than this
  search_results: 4
```

Send a document (PDF, DOCX, DOC, PPTX, PPT, TXT, MD, CSV, LOG) and it is chunked,
embedded and stored in ChromaDB; the bot gets a `semantic_search` tool and a list
of available files in its system prompt. Files placed in `./data/files/common/`
are ingested at startup and are visible to all users. `/listfiles` shows your
files, `/deletefiles` lets you delete them one by one or all at once (files,
vectors and registry).

`provider: local` computes embeddings on the bot's machine with the ONNX
MiniLM model bundled with ChromaDB — no API calls at all (the model, ~80 MB,
is downloaded on first use).

The configured embeddings identity (provider/model/base_url) is tracked in the
database: when it changes, the bot automatically drops the vector store on the
next start and re-embeds every registered file from disk (a registered file whose
source is missing is dropped from the registry with a log line). Depending on the
number of documents this can take a while on startup.

### mcp_servers (optional)

```yaml
mcp_servers:
  - name: filesystem                 # unique identifier, shown in /tools
    command: npx                     # stdio transport
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/data/shared"]
    env: {}
    timeout_seconds: 30
  - name: remote-search
    url: https://example.com/mcp     # streamable-http transport
    headers: {Authorization: "Bearer xxx"}
```

Each server needs exactly one of `command` (stdio) or `url` (streamable-http).
Servers are connected at startup; their tools are exposed to the model as
`mcp__<server>__<tool>`. A server that fails to connect is skipped with a log
line — the bot still starts. Users can switch whole servers on/off with `/tools`.

### proxies (optional)

```yaml
proxies:                    # http://user:pass@host:port; all optional
  telegram: null            # Telegram Bot API traffic
  llm: null                 # all OpenAI-compatible calls (chat, images, audio,
                            # embeddings); models[].proxy overrides per model
  search: null              # web search providers
  jina: null                # page opening (Jina Reader and the direct fallback)
```

### agent and logging

```yaml
agent:
  max_iterations: 5           # max tool-calling rounds per turn
  # max_turn_tokens: 30000    # token budget per turn; exceeded -> forced final answer
  tool_result_keep_chars: 300 # truncate older turns' tool results in history (0 = off)

logging:
  level: WARNING            # DEBUG | INFO | WARNING | ERROR | CRITICAL
  log_chats: false          # dump chats to ./data/chats on /delete
```

## Data and state

All state (chat history, per-user model/style/tool toggles, memory, statistics,
rate limiting, file registry) lives in a SQLite database at `./data/db.sqlite3`.
Uploaded files go to `./data/files/<user_id>/`, the ChromaDB vector store lives in
`./data/files/chromadb`. Logs rotate daily in `./logs`.

> Upgrading from the old (INI/pickle) version: there is no data migration. Create
> `data/config.yaml` from the example; the old `.config` and `data/tech/*.pickle`
> are ignored.

## Docker

Run the published image ([`sazonovanton/sirchatalot`](https://hub.docker.com/r/sazonovanton/sirchatalot)):

```
docker compose up -d
```

Or build from source:

```
docker compose -f docker-compose.build.yml up -d --build
```

Both compose files mount `./data` (config, database, files) and `./logs`. The
image includes ffmpeg (voice) and catdoc (legacy `.doc`/`.ppt` conversion); for
npx-based stdio MCP servers uncomment the nodejs block in the Dockerfile and
build your own image.

### Healthcheck

The image runs `healthcheck.py` every minute: the container is healthy while the
heartbeat file is fresh **and** the Bot API was reachable within
`SIRCHATALOT_HEARTBEAT_MAX_AGE` (default 300 s; keep it a few times
`telegram.network.heartbeat_seconds`). Check it with `docker ps` or:

```
docker inspect --format '{{json .State.Health}}' SirChatalot
```

Docker only *reports* unhealthy containers. To have one restarted automatically,
uncomment the `autoheal=true` label and the `autoheal` service in
`docker-compose.yml`.

## Development

Run the test suite (no network or API keys needed):

```
pip install -r requirements-dev.txt
python -m pytest
```

Live smoke checklist after changes: `/start`, a text message, `/model` switch +
another message, `/retry`, `/undo`, `/style`, a photo with a caption, a voice note,
`/imagine a cat`, send a PDF → `/listfiles` → ask a question about it →
`/deletefiles`, `/memory`, `/tools` toggle, `/statistics`, `/limit`, `/delete`.
For the fallback chain, point the first model at an invalid `base_url` and watch
the logs.

## Warnings

* The bot is not designed for group chats: state is kept per user, not per chat.
* Moderation (`chat.moderation`) uses the OpenAI moderation API and silently
  degrades to "pass" if the default model is not served by api.openai.com
  (a warning is logged at startup).
* MCP tools run with the bot's privileges — only add servers you trust, and
  remember users can invoke them through the model.

## License

Licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Acknowledgements

* [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
* [ChromaDB](https://www.trychroma.com/), [trafilatura](https://trafilatura.readthedocs.io/),
  [telegramify-markdown](https://github.com/sudoskys/telegramify-markdown)
