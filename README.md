# SirChatalot

A Telegram bot that proves you don't need a body to have a personality.

The bot talks to any **OpenAI-compatible** chat API — OpenAI, OpenRouter, local models
(Ollama, vLLM), or Anthropic / YandexGPT via their OpenAI-compatible endpoints. You can
configure several models at once, switch between them from the chat with `/model`, and
define a fallback chain that is tried automatically when the primary model errors out.

Features:
* **Multiple models** with per-user runtime switching (`/model`) and an optional fallback chain.
* **Agentic tool use**: the model can generate images, search the web, open URLs and
  search your uploaded documents — across several tool-calling iterations per turn.
* **MCP servers**: declare [Model Context Protocol](https://modelcontextprotocol.io)
  servers (stdio or streamable-http) in the config and their tools become available
  to the model. Users control which tools and MCP servers are active for them with `/tools`.
* **User memory**: the model saves lasting facts about the user (`save_memory` tool),
  they are injected into the system prompt; users view and delete them with `/memory`.
* **Smart history compaction**: instead of dropping old messages, older history is
  folded into a rolling summary that is updated incrementally; recent turns stay verbatim.
* **Documents / RAG**: send PDF, DOCX, PPTX, TXT and similar files; they are chunked,
  embedded and stored in ChromaDB. The bot searches them when answering (`/listfiles`,
  `/deletefiles`).
* **Vision**: send photos to vision-capable models.
* **Proper Telegram formatting**: model markdown is converted to valid MarkdownV2
  (code blocks, lists, quotes) with a plain-text fallback; the bot keeps the
  "typing…" indicator alive while generating.
* **/retry and /undo**: regenerate the last answer or remove the last exchange.
* **Web search providers**: Google CSE, SearXNG, Tavily or Brave; page opening
  goes through the Jina Reader (clean markdown) with a direct-fetch fallback.
* **Voice/video messages**: transcription via Whisper (or any compatible API), with
  optional transcript-only mode. Requires [ffmpeg](https://ffmpeg.org/).
* **Image generation** with `/imagine` (OpenAI images API: DALL-E etc.).
* **Styles** (bot personalities) switchable with `/style`.
* Whitelisting via access codes, banlist, per-user rate limits, usage statistics with
  cost estimates (`/statistics`).

## Getting started

1. Create a bot with [BotFather](https://t.me/botfather) and get the token.
2. Clone the repository and install dependencies: `pip install -r requirements.txt`
   (plus `ffmpeg` for voice support).
3. Copy `config.yaml.example` to `./data/config.yaml` and fill in your keys.
4. Run `python3 main.py`, or use Docker: `docker compose up -d`.

Validate your config without starting the bot:

```
python3 -m sirchatalot.config ./data/config.yaml
```

## Configuration

Everything is configured by a single YAML file, `./data/config.yaml`
(see `config.yaml.example` for a fully commented example).
Optional sections — `rate_limit`, `image_generation`, `audio`, `web`, `files` —
can be removed entirely to disable the feature.

The key section is `models`:

```yaml
models:
  - name: gpt-4o-mini          # display name for /model
    model: gpt-4o-mini         # model id sent to the API
    api_key: "sk-..."
    base_url: null             # null = api.openai.com; set for OpenRouter/Ollama/...
    prompt_price: 0.15         # USD per 1M tokens (for /statistics)
    completion_price: 0.6
    max_history_tokens: 16000
    vision: true               # can the model see images?
    tools: true                # does the model support tool calling?

default_model: gpt-4o-mini
fallback_chain: [claude-sonnet]   # tried in order on timeouts/rate limits/5xx
```

Users switch models with `/model`; the choice is stored per user. When a model
without vision or tools is selected, the history is adapted automatically
(images are replaced with placeholders, tool messages are flattened to text).

Bot personalities live in the `styles` section and are switched with `/style`
(switching a style clears the current session).

History compaction is tuned in `chat`: `summarize_too_long: true` enables the rolling
summary (`compact_threshold` — fraction of `max_history_tokens` that triggers
compaction, `keep_recent_messages` — how many recent messages stay verbatim).

User memory is enabled by the `memory` section (`max_items` per user). MCP servers
are listed under `mcp_servers`:

```yaml
mcp_servers:
  - name: filesystem
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/data/shared"]
  - name: remote-search
    url: https://example.com/mcp
    headers: {Authorization: "Bearer xxx"}
```

Each user can toggle individual built-in tools and whole MCP servers with `/tools`.

HTTP proxies can be set per traffic kind in the `proxies` section — `telegram`
(Bot API), `llm` (all OpenAI-compatible calls; a per-model `proxy` in `models[]`
overrides it), `search` (search providers) and `jina` (URL opening, both the
Jina Reader and the direct fallback). Format: `http://user:pass@host:port`.

Web search (`web.search`) supports four providers: `google` (api_key + cse_id),
`searxng` (instance `url`), `tavily` (api_key), `brave` (api_key). URL opening
(`web.url_open`) fetches pages through the [Jina Reader](https://jina.ai/reader)
by default (`via_jina: true`, optional `jina_api_key`) and falls back to a direct
SSRF-guarded fetch when Jina is unavailable. Set `via_jina: false` for fully local
operation: pages are extracted with trafilatura (main content as clean markdown,
boilerplate stripped).

Image generation works with the OpenAI images endpoint (`api: images` — OpenAI,
xAI, Together...) or through chat completions (`api: chat`) for OpenRouter image
models such as `google/gemini-2.5-flash-image`.

## Access control and limits

* `telegram.access_codes`: if set, the bot only answers whitelisted users; a user gets
  whitelisted by sending one of the codes. Whitelist is stored in `./data/whitelist.txt`.
* `telegram.banlist_enabled` + `./data/banlist.txt`: ban users by id.
* `rate_limit`: sliding-window per-user message limits with per-user overrides
  (`0` = unlimited). Check your usage with `/limit`.

## Data and state

All state (chat history, per-user model/style, statistics, rate limiting, file registry)
is stored in a SQLite database at `./data/db.sqlite3`. Uploaded files go to
`./data/files/<user_id>/`, the ChromaDB vector store lives in `./data/files/chromadb`.
Files placed in `./data/files/common/` are ingested at startup and become available
to all users. Logs rotate daily in `./logs`.

> Note: this version does not migrate data from the old pickle-based storage
> (`data/tech/*.pickle`) or the old INI config. Start from a fresh
> `data/config.yaml`; old files are simply ignored.

## Docker

```
docker compose up -d --build
```

The compose file mounts `./data` and `./logs`. The image includes ffmpeg and catdoc
(for legacy `.doc`/`.ppt` conversion).

## Smoke-test checklist

After changing the code, run `python -m pytest` and then check with a live token:
`/start`, a text message, `/model` switch + another message, `/style`, a photo with a
caption, a voice note, `/imagine a cat`, send a PDF → `/listfiles` → ask a question
about it → `/deletefiles`, `/statistics`, `/limit`, `/delete`. For the fallback chain,
point the first model at an invalid `base_url` and watch the logs.

## Warnings

* The bot is not designed for group chats: state is kept per user, not per chat.
* Moderation (`chat.moderation`) uses the OpenAI moderation API and requires an
  OpenAI key on the default model.
* Support for Stability AI and YandexART image generation was removed; use any
  OpenAI-compatible images API instead.

## License
Licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgements
* [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
* [OpenAI](https://openai.com/), [ChromaDB](https://www.trychroma.com/)
