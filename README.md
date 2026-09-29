# D.E.N.N.I.S

Windows desktop assistant with chat, provider routing, memory, browser, file, and desktop tools.

## Run

Double-click `run_dennis.bat` from Explorer, or run it from PowerShell. The launcher starts the GUI with the project-local `.venv_dennis` environment.

## Environment

Use CPython 3.13 x64 on Windows. Install the project dependencies into `.venv_dennis` with:

```powershell
.\.venv_dennis\Scripts\python.exe -m pip install -r requirements.txt
```

Configure provider API keys through environment variables or the corresponding files under `src/config/`. Do not commit credentials. The sentence-transformer model downloads on first use; OCR tools also require the Tesseract executable.

## Tool safety

File writes, file edits, and Python execution require explicit confirmation in the GUI. Python execution is not exposed to the model by default. Retrieved website, file, OCR, and clipboard content is treated as untrusted data.

## Tests

Run the automated suite with:

```powershell
.\.venv_dennis\Scripts\python.exe -m pytest -q
```
