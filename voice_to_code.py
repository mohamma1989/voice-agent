import os
import sys
import time
import queue
import threading
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from google import genai
from google.genai import types

# ----------------- Terminal Styling -----------------
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def status_log(tag, msg, color=CYAN):
    print(f"{color}{BOLD}[{tag}]{RESET} {msg}", flush=True)

# ----------------- Setup & Config -----------------
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print(f"{RED}[ERROR] GEMINI_API_KEY is not set. Run: export GEMINI_API_KEY='key'{RESET}")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

status_log("INIT", "Loading local Whisper engine (runs 100% offline)...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
status_log("READY", "Whisper is loaded and ready.\n", GREEN)

AUDIO_FILE = "input.wav"
SAMPLE_RATE = 16000

# ----------------- Audio Recording -----------------
def record_audio(prompt_msg="[REC] Recording... Speak now. Press [ENTER] when done."):
    q = queue.Queue()
    stop_event = threading.Event()

    def callback(indata, frames, time_info, status):
        q.put(indata.copy())

    print(f"\n{RED}{BOLD}{prompt_msg}{RESET}", flush=True)

    def wait_for_enter():
        input()
        stop_event.set()

    t = threading.Thread(target=wait_for_enter, daemon=True)
    t.start()

    with sf.SoundFile(AUDIO_FILE, mode='w', samplerate=SAMPLE_RATE, channels=1, subtype='PCM_16') as file:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=callback):
            while not stop_event.is_set():
                while not q.empty():
                    file.write(q.get())

    status_log("AUDIO", "Microphone stream closed.", GREEN)

def transcribe():
    status_log("STT", "Transcribing speech (locally) ...")
    segments, _ = whisper_model.transcribe(
        AUDIO_FILE,
        language="en",
        vad_filter=True,
        condition_on_previous_text=False
    )
    text = " ".join([s.text for s in segments]).strip()
    return text

# ----------------- Gemini Code Generation -----------------
def generate_code_with_spinner(prompt_text):
    system_prompt = (
        "You are an autonomous Python automation assistant. "
        "The user will describe a task or file operation. "
        "Return ONLY pure, executable Python code. "
        "Do NOT include markdown fences (```), comments, or conversational text. "
        "Just executable code."
    )

    # Primary model with automatic fallback
    MODELS_TO_TRY = ["gemini-3.8-flash", "gemini-2.5-flash"]
    result_container = {"code": None, "error": None, "active_msg": "Connecting to Gemini..."}

    def api_worker():
        for model_name in MODELS_TO_TRY:
            for attempt in range(3):
                try:
                    result_container["active_msg"] = f"Calling {model_name} (attempt {attempt + 1})..."
                    res = client.models.generate_content(
                        model=model_name,
                        contents=f"Task: {prompt_text}",
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=0.1,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                        )
                    )
                    raw = res.text.strip()
                    if raw.startswith("```"):
                        lines = raw.split("\n")
                        raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
                    result_container["code"] = raw
                    return  # Success, exit immediately
                except Exception as e:
                    err_str = str(e)
                    if "503" in err_str or "UNAVAILABLE" in err_str:
                        # Server busy; wait briefly before retrying
                        time.sleep(2)
                        continue
                    else:
                        result_container["error"] = err_str
                        return
        result_container["error"] = "All retry attempts and fallback models were busy (503). Please try again."

    worker_thread = threading.Thread(target=api_worker, daemon=True)
    worker_thread.start()

    spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    idx = 0
    while worker_thread.is_alive():
        msg = result_container.get("active_msg", "Generating code...")
        sys.stdout.write(f"\r{CYAN}{spinner_chars[idx % len(spinner_chars)]}{RESET} {msg} ")
        sys.stdout.flush()
        idx += 1
        time.sleep(0.08)

    sys.stdout.write("\r" + " " * 65 + "\r")
    sys.stdout.flush()

    if result_container["error"]:
        status_log("ERROR", f"API request failed: {result_container['error']}", RED)
        return None

    return result_container["code"]

# ----------------- Main Loop -----------------
if __name__ == "__main__":
    while True:
        try:
            print(f"\n{BOLD}{'=' * 60}{RESET}")
            
            # --- Transcription & Retry Loop ---
            confirmed_prompt = None
            while not confirmed_prompt:
                input(f"{YELLOW}{BOLD}[ACTION]{RESET} Press {BOLD}[ENTER]{RESET} to start recording your voice command...")
                record_audio("[🎤 REC] Listening... Speak clearly, then press [ENTER] to stop.")
                
                text = transcribe()
                if not text:
                    status_log("WARN", "No speech detected. Try speaking closer to the mic.", YELLOW)
                    continue

                print(f"\n{BOLD}Captured Speech:{RESET} \"{CYAN}{text}{RESET}\"")
                
                # Verify transcription before sending to Gemini
                verify = input(f"{YELLOW}[?] Is this transcription correct? [Y/n] (press Enter or 'y' to proceed, 'n' to re-record): {RESET}").strip().lower()
                
                if verify in ["", "y", "yes"]:
                    confirmed_prompt = text
                else:
                    status_log("RETRY", "Discarded transcription. Let's record again.", YELLOW)

            # --- LLM Generation ---
            code = generate_code_with_spinner(confirmed_prompt)
            if not code:
                continue

            print(f"\n{GREEN}{BOLD}┌─── GENERATED PYTHON SCRIPT ({len(code.splitlines())} lines) ──────────────────────────┐{RESET}")
            for line in code.splitlines():
                print(f"│  {line}")
            print(f"{GREEN}{BOLD}└───────────────────────────────────────────────────────────────┘{RESET}\n")

            # Final execution confirmation
            choice = input(f"{YELLOW}[?] Execute this script into task.py? [y/N]: {RESET}").strip().lower()
            if choice == "y":
                with open("task.py", "w") as f:
                    f.write(code)
                status_log("SUCCESS", "Wrote to 'task.py'! Watcher will execute it inside test-project/ now.", GREEN)
            else:
                status_log("CANCEL", "Execution canceled. Nothing was written.", YELLOW)

        except KeyboardInterrupt:
            print(f"\n{RED}[!] Exiting voice agent.{RESET}")
            break
