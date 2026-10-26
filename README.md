# Parlo

Private, offline dictation for Windows. Press a shortcut, speak, and your words are typed
into whatever app you are using. It also has voice notes with formatting, and can read text
aloud. Everything runs on your own PC; your audio never leaves the computer.

## Install (once)

1. Unzip the folder somewhere permanent, for example `Documents\Parlo`.
2. Double-click **Setup.bat**. The Parlo installer opens: press **Install** and watch each step
   tick off. It downloads about 2.3 GB the first time (Python 3.11, PyTorch, the speech
   libraries, the 156 MB Bark 3.0 speech model and the 1 GB AI writing model), puts everything
   inside this folder, then unpacks the speech model once. It takes 15 to 30 minutes. If a step
   fails (for example the internet drops), press **Try again**: finished steps are kept.
   *Show details* shows the full log, which is also saved to `data\setup-log.txt`.
   - If Windows SmartScreen warns about the file, choose *More info* then *Run anyway*.
   - If Python 3.11 cannot be installed automatically, install it from python.org
     (tick "py launcher") and run Setup.bat again.
3. Start **Parlo** from the Desktop shortcut (or `Start Parlo.bat`).

The model takes about 20 seconds to load at each start. A microphone icon sits in the system
tray; closing the window keeps the app running there (right-click the icon to quit).

## Use

| Do this | What happens |
|---|---|
| Tap **Ctrl + Win** | Start recording. Tap again to stop and insert the text. |
| Hold **Ctrl + Win** while talking | Push-to-talk: release to stop and insert. |
| **Esc** while recording | Cancel. |
| Select text, press **Ctrl + Alt + R** | Read the selection aloud. Press again to stop. |
| Select text, press **Ctrl + Alt + Space**, say how to change it | Edit by voice: "make this more formal", "shorten this", "translate into French". |
| End a dictation with "send it" or "press enter" | The text is typed, then Enter is pressed. |
| Say only "undo that", "scratch that" or "select all" | Parlo does it instead of typing the words. |

The first time Parlo opens, a short walkthrough checks your microphone and has you try a first
dictation. You can see it again from Settings.

### The window

- **Home**: your shortcut, the default AI mode, stats (words today, time saved), your activity
  (a 14-day chart, your daily streak, how fast you speak and the apps you dictate into most) and
  recent dictations. *Transcribe a file* turns an audio or video file (wav, mp3, m4a, mp4…) into text.
- **AI modes**: have an AI polish what you said before it's inserted (see below).
- **Notes**: voice notes with formatting. Press **Dictate**, talk, press it again. Use the
  toolbar for bold, italic, headings, bullet, numbered and check lists, and quotes. Notes save
  automatically and can be copied, read aloud or saved as Markdown. **Record a meeting** turns a
  meeting or lecture into a note: the transcript is added every 30 seconds with timestamps, and
  when you stop, the on-PC AI adds a summary and action items at the top.
- **History**: every dictation, searchable, with copy, read-aloud and delete.
- **Read aloud**: paste text and hear it with any Windows voice.
- **Models**: choose and download speech models (see below).
- **Settings**: shortcuts (click *Change* and press the new keys), activation mode, what
  happens after transcribing, microphone, sounds, word replacements, the recording indicator
  (bottom pill, top capsule, small dot or off, with optional live text), language, voice
  actions, your personal dictionary, start with Windows, a floating mic button, sync between PCs,
  and dark/light theme.

### Personal dictionary

In Settings, list the names and jargon Parlo should spell right, one per line (product names,
colleagues, places). Close mistakes are corrected ("Paulo" becomes *Parlo*, "Kubanetis" becomes
*Kubernetes*, "git hub" becomes *GitHub*); ordinary words are never changed, so "parlour" stays
"parlour". Whisper models are also told to expect the words.

### Floating mic button

Turn on *Floating mic button* in Settings for a small Parlo button that stays on top of other
windows: click it to start and stop dictating, drag it anywhere, right-click to hide it. It never
takes focus, so your words still go to the app you were typing in.

### AI modes

Modes rewrite your dictation with an AI before it's typed: **Clean up** (removes "um", false
starts, fixes grammar), **Email**, **Bullet notes**, **Professional**, or any mode you write
yourself ("Translate into Spanish", "Write it as a tweet"…). *Plain dictation* uses no AI.

Each mode can also be tied to apps (*Use automatically in*): for example *Email* in Outlook and
*Clean up* in Slack. Dictating into those apps then uses that mode without switching by hand.

By default this runs **free on your own PC**: a small AI writing model is downloaded during
setup and nothing is sent anywhere. Pick a mode on Home and dictate as usual.

| On-PC AI model | Download | RAM while in use | Clean-up time* | Best for |
|---|---|---|---|---|
| **Qwen2.5 1.5B** (default) | 1.0 GB | ~1.7 GB | 1-2 s | Everyday PCs; fast clean-ups and lists |
| Qwen3 1.7B | 1.7 GB | ~2 GB | 3-4 s | Keeping closest to your own words |
| Qwen3 4B | 2.3 GB | ~3.5 GB | ~8 s | Best writing (emails); 16 GB PCs |

\*Measured on a 6-core Intel i5 without a graphics card (Qwen3 4B estimated). All Apache-2.0.

Download or switch models in **AI modes**. The model loads while you're still speaking and is
unloaded after 5 idle minutes, so it only uses memory when you use it.

Optional: you can choose an online service instead (*Runs on* menu): Groq or Google Gemini (free
tiers), OpenAI or Anthropic (pay per use), or your own Ollama. Paste its API key (stored encrypted
on this PC) and press **Test**. Then only the *text* is sent to that service, never your audio.
If the AI fails for any reason, the plain transcript is inserted instead.

### Natural voices for read-aloud

On **Read aloud**, choose **Natural voices** and download them once (116 MB). Parlo then reads
with lifelike Kokoro voices (37 voices in US/UK English, Spanish, French, Italian and Portuguese)
instead of the robotic Windows ones, still entirely on your PC. Press **Try** to hear a voice.
Reading starts after about a second (a few seconds the very first time while the voice loads).

### Bring your own models (Advanced)

For more powerful PCs, both model lists accept your own models. They are marked *Your model ·
untested*, and Parlo warns you if one probably won't fit in your PC's free memory.

- **AI writing models** (AI modes page): *From Hugging Face* takes any repo with GGUF files, e.g.
  `Qwen/Qwen3-8B-GGUF`, and lets you pick a size (Q4_K_M is a good balance). *Choose a .gguf file*
  uses a model you already have; Parlo reads it where it is and never deletes it.
- **Transcription models** (Models page): *Add a Whisper model* takes any faster-whisper
  (CTranslate2) repo, e.g. `Systran/faster-distil-whisper-large-v3`, or a fine-tune for your language.

### Sync between PCs

In Settings, *Choose sync folder* and pick a folder that OneDrive, Google Drive or Dropbox keeps
in sync. Do the same on the other PC (pick the same synced folder). Notes, history, AI modes and
most settings are then shared; the microphone, speech model and API key stay per PC.

### Formatting notes by voice

Pause briefly, then say the command; keep talking after it.

| Say | You get |
|---|---|
| "new paragraph" | a new paragraph |
| "new line" | a line break |
| "bullet point" | a bulleted list item |
| "numbered point" | a numbered list item |
| "new heading" | a heading (the words after it) |
| "end list" | back to normal paragraphs |

Example: *"Shopping list. Bullet point milk. Bullet point bread. New paragraph. Call the plumber
on Monday."*

## Speech models

| Model | Download | RAM in use | Languages | Notes |
|---|---|---|---|---|
| **Bark 3.0** (default) | 156 MB | ~3.2 GB | English | Most accurate English for its size |
| Bark 3.0 Plus | 171 MB | ~3.3 GB | English | Slightly more accurate |
| Whisper Base | 141 MB | ~1.2 GB | English | Fast and light; more mistakes |
| Whisper Small | 461 MB | ~1.6 GB | English | Middle ground |
| Whisper Large v3 Turbo | 1.5 GB | ~2.6 GB | 99 languages | For other languages; slower on CPU |

For languages other than English, use Whisper Large v3 Turbo and set *Language* in Settings
(or leave it on *Detect automatically*).

Switch models on the **Models** page. The model runs in its own background process, so
switching really frees the old model's memory.

## Requirements

- Windows 10 or 11, 64-bit, a microphone, about 5 GB free disk space (more for extra models).
- Free RAM for the model you pick (table above), plus about 0.3 GB for the app. With Bark,
  8 GB total is tight and 16 GB is comfortable; Whisper Base suits 8 GB PCs.
- No graphics card needed. On a 6-core CPU, 9 seconds of speech takes about 1 second.

## Troubleshooting

- **Nothing is typed**: some apps run as administrator and ignore input from normal apps.
  Set *Insert by* to *Type*, or *After transcribing* to *Copy to clipboard only*.
- **Wrong microphone**: pick it in Settings.
- **Model problem**: the status card at the bottom left turns red; open Models for details.
- **Check the model works**: `.venv\Scripts\python.exe app\selftest.py` (a Windows voice
  says a sentence and Bark transcribes it).
- **Logs**: `data\parlo.log` (app) and `data\engine.log` (speech model).
- **Uninstall**: turn off *Start with Windows* in Settings, quit from the tray icon, then delete
  this folder and the two `Parlo` shortcuts (Desktop and Start Menu).

## Credits and licences

- [Underdog Bark 3.0](https://huggingface.co/ConwayResearch/Underdog-Bark-3.0) and
  [Bark 3.0 Plus](https://huggingface.co/ConwayResearch/Underdog-Bark-3.0-Plus) by Conway
  Research, derived from NVIDIA `parakeet-tdt-0.6b-v3` and `moondream/parakeet-ultra`.
  CC-BY-4.0; attribution in each model folder's `NOTICE`.
- OpenAI Whisper models in CTranslate2 format via
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT).
- AI writing models: Qwen2.5 1.5B Instruct, Qwen3 1.7B and Qwen3 4B by the Qwen team (Alibaba),
  Apache-2.0, run with [llama.cpp](https://github.com/ggml-org/llama.cpp) via llama-cpp-python (MIT).
- Models download from Hugging Face at pinned versions; none are shipped in this folder.
- Read-aloud uses the speech voices built into Windows, or Kokoro-82M (Apache-2.0) through
  kokoro-onnx (MIT). Kokoro's pronunciation step uses espeak-ng and phonemizer, which are
  GPL-3.0: fine for personal use and sharing, but check before selling a closed-source version.
- An independent app modelled on how Spokenly and Wispr Flow behave. It contains no code or
  assets from either and is not affiliated with them.
