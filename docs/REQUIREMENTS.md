# Requirements and roadmap

## Implemented version 0.1

Windows 11 x64 desktop application; manual launch and system tray; text and push-to-talk; English/Filipino/Taglish prompts and multilingual local transcription; bilingual cloud speech with English Windows fallback; cloud-first free-tier configuration with local Qwen3 fallback; registered app commands; approved folder search; TXT/MD/DOCX/text-PDF extraction; public research with source records; note editing/export; explicit memory editing/deletion; local history; outbound approval; task cancellation and activity; portable one-folder packaging.

Cloud services require a user-supplied free-tier key and eligibility. Macooii does not verify billing state or guarantee continuing free quotas. Reviewed model IDs are selectable; no automatic paid replacement is used.

## Acceptance targets

- At least 90% correct intent and target selection on representative English/Taglish text and real-user voice requests, with clarification for ambiguity. A real-user evaluation set is needed; unit tests alone do not establish this target.
- No personal source content sent without recipient/payload approval. Private earlier turns excluded from later cloud history.
- Revoked folders cannot be read. Unregistered applications and undeclared tools cannot execute.
- Cancellation prevents later actions. Cloud fallback cannot duplicate completed writes.
- Citations correspond to retrieved sources. Format limits, truncation, quota failures, inaccessible files, blocked pages, and missing models are visible.
- UI remains responsive during inference, browser, extraction, and speech work. Measure latency on actual hardware rather than promise fixed cloud performance.

## Next release

Reminders and tasks, daily briefings, wake-word activation with visible listening state, scanned-document OCR, and improvements based on real Taglish recordings and task evaluations.

## Later

Calendar/email services, additional music services, authenticated browser workflows, reusable workflows, visual desktop control, phone access, smart-home control, and proactive suggestions. Each requires separate service and permission decisions.

Version 0.3 adds spoken reply output selection and testing, actual Windows speech text for Taglish replies, public website navigation, and verified YouTube play/pause/resume/stop workflows in an owned visible browser.
