# Architecture

PySide6/QML provides the interface. A QObject bridge exposes state and user actions through Qt signals and slots. Blocking work runs in a thread pool with one active user task. Speech-model downloading runs in a separate, cancellable process.

## Task flow

1. Save the new user turn locally, initially marked private.
2. Handle explicit local commands without contacting an AI model.
3. Select Gemini or Ollama. Attach only non-private earlier turns to cloud requests.
4. Send declared JSON-schema tools. Preserve Gemini function-call content/signatures between turns.
5. Validate tool arguments, app intent, current folder permissions, and cancellation before execution.
6. Hold private results until exact recipient/payload approval. A local-mode choice transfers the existing task and result to Ollama without replaying the action.
7. Continue until an answer, cancellation, failure, or tool-step limit. Cache tool results within the task so repeated requests cannot duplicate writes.
8. Save the answer and its sensitivity marker. Render citations from fetched source records. Prepare short spoken output when enabled.

## Components and interfaces

- **Engine:** coordinates provider selection, tool requests, permissions, fallback, and step limits.
- **Provider adapters:** convert neutral messages to fixed-endpoint Gemini or local Ollama requests. Return text and structured tool calls; never execute them.
- **ToolRegistry:** registered app commands, opaque file handles, public web retrieval, notes, and memory reads. Explicit memory writes are handled locally from user instructions or the Memory screen.
- **TaskContext:** cancellation, exact-recipient/payload approvals and declines, source records, and local cards. Replaced for every task.
- **Store:** parameterized SQLite queries, WAL, notes, messages, preferences, activity, and FTS5 indexes. API keys use a separate OS keyring adapter.
- **Browser:** short-lived unauthenticated Chrome/Edge contexts, public HTTP(S) destinations, no personal profile, and GET/HEAD requests only.
- **Speech:** in-memory microphone samples, local Whisper transcription, text-only cloud synthesis, and Windows speech fallback.

There is no public HTTP server or remote app API. Ollama is reached only at `127.0.0.1:11434`. File IDs are session-scoped and folder permissions are rechecked on every read. Removing folders clears the extracted text index.

## Failure handling

Automatic mode can fall back to Ollama after cloud quota, connectivity, access, or model failures. Cloud-only mode reports failure. Local-only mode does not use Gemini, including for speech. Failed operations produce safe tool errors. Cancellation is cooperative for in-flight requests and checked before subsequent actions; completed actions are not rolled back. Source content and credentials are excluded from diagnostic logs.

Models are external resources, not included in the ZIP. Ollama's lifecycle is independent of Macooii.

## Codex provider (v0.2)

The Codex adapter starts the installed native CLI app-server over stdio, verifies `account/read` reports a ChatGPT login, and requests schema-constrained decisions. Each inference step uses a fresh ephemeral thread with environments disabled. Native shell, plugins, connectors, hooks, memory, browser, and delegation features are disabled. Inherited MCP names are disabled both at CLI startup (bare names) and in the thread's JSON configuration. Built-in provider selection is forced to OpenAI and API-key environment variables are removed from the child.

The model receives only the conversation selected by Macooii's history policy and its tool catalog. The response selects one declared Macooii function or returns an answer. No Codex-native tool requests are accepted. All real execution and outbound approvals remain in Engine/ToolRegistry/TaskContext. A failed inference can fall back to local AI without replaying completed writes. Speech in this mode stays on Windows; it does not use a saved Gemini key.

## Visible actions and voice (v0.3)

A dedicated thread owns Playwright's persistent visible Chrome/Edge context and processes browser jobs. Public HTTP(S) navigation and defined YouTube playback controls are exposed as validated Macooii tools. Playback success requires a ready, unpaused video element. Private-derived outbound queries retain exact-payload approval. Clear commands bypass model inference; model decisions use the same tools and intent guard. Downloads are canceled. This is separate from headless research and the user's normal browser profile.

Windows SAPI generates a temporary WAV through late-bound COM on a worker thread. Qt Multimedia plays both local and cloud WAVs through the selected output device, with explicit volume and mute state. The Settings voice test exercises this same path. Temporary audio is deleted on completion, cancellation, shutdown, or stale-cache startup cleanup. No microphone capture is needed to test reply speech.

Version 0.3.2 routes ordinary website opening to the registered regular Chrome/Edge executable (Windows default-browser fallback), with no automation profile arguments or tab access. Browser app opening requests a regular new window instead of focusing any matching executable. Controlled YouTube playback continues using the dedicated persistent profile; its authentication remains separate. Website tools report a launch request rather than claiming page-load verification in an uncontrolled browser.

Version 0.3.3 also routes compound YouTube playback commands through the regular browser. A bounded, unauthenticated HTTP search resolves an organic video ID; failure returns a search URL. The tool distinguishes requested playback from search fallback and never asserts verified playing state. Regular-browser pause/resume/stop is unavailable. Earlier controlled-profile playback is superseded for user-facing music commands.

## Facebook capture reader (v0.4)

A Manifest V3 extension uses explicit activeTab permission to extract rendered Facebook text or the current selection. It sends a bounded message to a fixed-origin Chrome native messaging host. The standalone console host validates and atomically queues the capture in the current user's local Macooii directory; the desktop process polls the inbox and displays a local preview. Browser credentials and cookies are never copied.

Summarization is a separate user action. The capture is validated again, marked private, and shown for exact cloud-recipient approval before model use. Local processing and cancellation remain available. This summary path has no tool schemas, executes no tools, and treats captured text as untrusted data. Raw captures are not copied into conversation history. The host uses stdio framing and has no HTTP listener. Registry setup is per-user and allowed_origins is restricted to the fixed extension ID.

## Local neural speech and voice conversation (v0.5)

A cached CPU ONNX session generates Kokoro audio locally, using a four-thread session and pinned model/voice hashes. Model assets are explicitly downloaded outside the application bundle. eSpeak NG data and DLLs, Kokoro vocabulary data, package metadata and third-party notices are included in the portable application. The same Qt playback device path is used for neural, Windows and cloud output. Cancellation is checked before/after inference and immediately stops current playback; an in-flight inference may need time to return.

Conversation mode is opt-in in the app and skips transcript review. A recognized utterance is held until the transcription job's finished event, then submitted only if uncanceled. Interruption cancels the existing task and records only if the talk control remains held when the old task finishes. Releasing or canceling clears that pending recording request. Existing approval gates for private sources remain unchanged.

## Microphone and Taglish recognition (v0.6)

The recorder prefers the WASAPI default when no explicit microphone is selected, captures at its native sample rate, and uses PyAV's resampler for the 16 kHz recognizer input. Stereo fallback selects the stronger channel to avoid opposite-phase cancellation. Audio remains bounded to 60 seconds in RAM. Live level, clipping, overflow and signal-strength information are calculated without saving raw audio.

Whisper recognition supports the existing Small model and a pinned local Large v3 Turbo snapshot. Taglish maps to Filipino transcription with mixed-language hints, deterministic decoding, short-utterance VAD padding and word-level estimates. Poor capture quality or low model confidence prevents automatic voice submission. A user-triggered five-second microphone test always returns a reviewable transcript and cannot execute it. Large model files use bounded resumable HTTP ranges, atomic installation and SHA256 verification.

## Voice console (v0.7)

The QML Assistant page uses a procedural Canvas sphere and instrument rings, a compact command dock, a secondary history panel, and a full-response overlay. Canvas motion runs at a bounded 25 frames per second and pauses for hidden/minimized windows. Playback state and RMS energy are exposed by Bridge from QMediaPlayer and QAudioBufferOutput. Microphone energy comes from the existing recorder. The UI retains typed input, reviewed transcripts, source cards and the existing approval overlays. Stored messages remain in the same database and are not erased by the presentation change.
