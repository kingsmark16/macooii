# Macooii

A Windows personal AI assistant with an animated voice interface, press-to-talk conversation, local speech recognition and synthesis, public web research, approved document access, notes, and explicit memory.

## Run

Open **Launch Macooii.cmd**, or extract the portable Windows ZIP and run `Macooii.exe`. Keep the complete application folder together.

From source with Python 3.12:

```powershell
uv sync --frozen --python 3.12
uv run --frozen macooii
```

## Set up

- Choose Codex to use an existing ChatGPT CLI login and available plan allowance. Install the official Codex CLI, run `codex login`, then use **Check Codex** in Settings. No API key is required for this provider.
- Alternatively configure Gemini with your own API key, or install Ollama and the selected local model. Provider quotas and billing terms apply.
- Download the selected recognition model and optional natural voice assets from Settings. Downloads are explicit; models are excluded from the repository and portable archive.
- Select the microphone, reply speakers, recognition language, voice, and speaking pace. Test microphone input before enabling automatic transcript submission.
- Approve folders and register applications you want the assistant to access.

## Voice and commands

Hold the talk control or configured shortcut, speak, then release. Conversation mode submits recognized text automatically; review mode places it in the composer. Uncertain or poor-quality recordings require review. Hold the control again to interrupt; Stop cancels further actions and queued speech.

Quick acknowledgments play while processing. Local models load in the background and spoken answers use short ordered chunks. Full response latency depends on model size, hardware, network, and tools. App and website action announcements finish before the action executes. Completed actions cannot be undone by cancellation.

Generic command examples:

- Open a registered application.
- Find a document in an approved folder.
- Research a topic and summarize verified sources.
- Save a note with a title and body.
- Open YouTube and play instrumental music.

Use `/help` for available commands. Notes, Memory, Activity, Settings, and conversation History remain accessible from the interface.

## Browser reader

The optional **Read with Macooii** extension captures loaded text or selected text from the Facebook tab you choose. Run **Install Browser Bridge.cmd** from the portable folder, load `browser-extension` through Chrome's extensions page, then review a capture in the app before requesting a summary. Cloud summaries require approval of the exact captured context. Opening a website alone does not grant access to its signed-in contents. Music playback requests open regular Chrome; actual playback and account state are not verified.

## Local data and privacy

User state lives outside the repository in `%LOCALAPPDATA%/Macooii`, optionally overridden with `MACOOII_DATA_DIR`. The local database is `macooii.db`; API credentials use Windows Credential Manager. The database relies on Windows account permissions and is not separately encrypted.

Conversation and activity retention is limited. Saved notes and explicit memories remain until removed. Private source excerpts require approval before cloud processing. Raw microphone capture is kept in memory. Temporary synthesized speech is removed after playback or cancellation. Fixed public acknowledgment phrases may be cached locally. Browser captures expire or are discarded after review.

The repository contains source code, generic synthetic test fixtures, documentation, and required third-party notices. It excludes credentials, local databases, recordings, browser profiles, model files, and generated diagnostics. Test fixtures are illustrative and do not represent user activity.

## Development

```powershell
uv run --frozen pytest -q
uv run --frozen ruff check src tests tools
uv run --frozen python tools/build.py
```

The build produces `dist/Macooii`, `dist/Macooii-Windows-x64.zip`, and `dist/SHA256.txt`. Build outputs are excluded from Git. Dependency notices and required corresponding source archives are included under `docs/third-party`.

See [Architecture](docs/ARCHITECTURE.md), [Requirements](docs/REQUIREMENTS.md), and [Validation](docs/VALIDATION.md). Synthetic tests do not establish real-microphone accuracy or guaranteed response times.
