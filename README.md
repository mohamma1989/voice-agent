# Voice-Driven Autonomous Code Agent

An event-driven Linux automation tool that listens to natural voice instructions, converts speech to text locally, uses **Gemini 3.8 Flash** to generate pure executable Python scripts, and automatically executes them inside a dedicated sandbox directory.

---

## Architecture Overview

```text
       [Microphone]
            │
            ▼ (16kHz Audio)
  [Local faster-whisper]          <-- 100% Offline & Open Source (No API cost)
            │
            ▼ (Transcribed Command)
  [Human-in-the-Loop Review]       <-- Terminal confirmation & edit check
            │
            ▼
   [Gemini 3.8 Flash]             <-- Generates executable Python (No fences, pure code)
            │
            ▼
        task.py                   <-- Writes atomically to File A (POSIX truncate)
            │
       (inotify event)
            │
            ▼
     [watcher.py]                 <-- Intercepts event & executes task.py inside ./test-project/