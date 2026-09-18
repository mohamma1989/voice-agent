import os
import threading
import queue
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")

client = genai.Client(api_key=API_KEY)

print("[*] Loading Whisper model (base)...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

AUDIO_FILE = "input.wav"
SAMPLE_RATE = 16000

def record_audio_until_enter():
    q = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata.copy())

    print("\n[🎤 REC] Speak now. Press [ENTER] as soon as you finish speaking!")
    stop_event = threading.Event()

    def wait_for_enter():
        input()
        stop_event.set()

    threading.Thread(target=wait_for_enter, daemon=True).start()

    with sf.SoundFile(AUDIO_FILE, mode='w', samplerate=SAMPLE_RATE, channels=1, subtype='PCM_16') as file:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=callback):
            while not stop_event.is_set():
                while not q.empty():
                    file.write(q.get())

    print("[✔] Recording captured.")

def transcribe_audio():
    print("[*] Transcribing speech...")
    # vad_filter=True removes background silence and loops
    # language="en" stops Whisper from guessing Arabic or repeating words
    segments, info = whisper_model.transcribe(
        AUDIO_FILE,
        language="en",
        vad_filter=True,
        condition_on_previous_text=False
    )
    text = " ".join([s.text for s in segments]).strip()
    return text

def generate_script(prompt_text):
    print(f"[*] Sending prompt to Gemini: \"{prompt_text}\"")
    
    system_prompt = (
        "You are an autonomous Python automation assistant. "
        "The user will describe a task or file operation. "
        "Return ONLY pure, executable Python code with no markdown fences, no backticks, and no explanations."
    )

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=f"Task: {prompt_text}",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="OFF"
                )
            )
        )
    )

    code = response.text.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    return code

if __name__ == "__main__":
    while True:
        try:
            input("\nPress [ENTER] to record (or Ctrl+C to exit)...")
            record_audio_until_enter()
            
            prompt = transcribe_audio()
            if not prompt:
                print("[-] No speech detected. Please speak closer to the mic.")
                continue

            print(f"\n[SPEECH TRANSCRIBED]: \"{prompt}\"")
            
            # Generate code without writing yet
            code = generate_script(prompt)

            print("\n" + "=" * 20 + " GENERATED CODE " + "=" * 20)
            print(code)
            print("=" * 56)

            # Confirm before touching task.py
            choice = input("\nExecute this? [y/N]: ").strip().lower()
            if choice == "y":
                with open("task.py", "w") as f:
                    f.write(code)
                print("[✔] task.py updated! Watcher is executing it now.")
            else:
                print("[✖] Discarded. Nothing was written.")

        except KeyboardInterrupt:
            print("\nExiting.")
            break
