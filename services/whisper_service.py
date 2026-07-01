from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


APP_DIR = Path(__file__).resolve().parents[1]

load_dotenv(APP_DIR / ".env")
load_dotenv()


def _read_secret_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_secret(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    for path in (
        APP_DIR / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ):
        data = _read_secret_file(path)
        if data.get(name):
            return str(data[name])
    return default


def _transcribe_with_whisper_cpp(audio_path: Path, language: str) -> str:
    binary = _get_secret("WHISPER_CPP_BIN") or shutil.which("whisper-cli") or shutil.which("whisper-cpp")
    model = _get_secret("WHISPER_CPP_MODEL")
    if not binary or not model:
        return ""

    output_txt = audio_path.with_suffix(audio_path.suffix + ".txt")
    cmd = [
        binary,
        "-m",
        model,
        "-l",
        language,
        "-otxt",
        "-nt",
        "-f",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0 or not output_txt.exists():
        return ""
    try:
        text = output_txt.read_text(encoding="utf-8").strip()
    finally:
        try:
            output_txt.unlink()
        except OSError:
            pass
    return text


def transcribe_audio(audio_path: str | Path, language: str = "ko") -> str:
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    local_text = _transcribe_with_whisper_cpp(path, language)
    if local_text:
        return local_text

    api_key = _get_secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    model = _get_secret("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
    client = OpenAI(api_key=api_key)
    with path.open("rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            language=language,
            response_format="text",
        )
    return str(result).strip()
