from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


APP_DIR = Path(__file__).resolve().parents[1]
OPENAI_AUDIO_MAX_BYTES = 24 * 1024 * 1024
DEFAULT_TRANSCRIBE_PROMPT = (
    "Korean phone-call transcription. Preserve natural spoken Korean. "
    "This is for sales and business call notes. Common terms include: "
    "계약서, 견적서, 발주서, 제안서, 미팅, 회의, 자료, 준비, 고객사, 담당자, "
    "오전, 오후, 내일, 일정, 회식, 치킨. "
    "Prefer 계약서 over 대학서 when the context is business documents."
)

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


def _ffmpeg_bin() -> str:
    return _get_secret("FFMPEG_BIN") or shutil.which("ffmpeg") or ""


def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        message = detail[-1] if detail else "ffmpeg failed"
        raise RuntimeError(message[:500])


def _prepare_openai_audio_files(audio_path: Path, work_dir: Path) -> list[Path]:
    max_bytes = int(_get_secret("OPENAI_AUDIO_MAX_BYTES", str(OPENAI_AUDIO_MAX_BYTES)))
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        if audio_path.stat().st_size > max_bytes:
            raise RuntimeError("Audio file is too large for OpenAI transcription and ffmpeg is not installed.")
        return [audio_path]

    converted = work_dir / "call_16k_mono.mp3"
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        str(converted),
    ])
    if converted.exists() and converted.stat().st_size <= max_bytes:
        return [converted]

    chunk_pattern = str(work_dir / "chunk_%03d.mp3")
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "32k",
        "-f",
        "segment",
        "-segment_time",
        "600",
        "-reset_timestamps",
        "1",
        chunk_pattern,
    ])
    chunks = sorted(work_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("ffmpeg did not create transcription chunks.")
    oversized = [chunk.name for chunk in chunks if chunk.stat().st_size > max_bytes]
    if oversized:
        raise RuntimeError(f"Audio chunk is still too large for OpenAI transcription: {oversized[0]}")
    return chunks


def _transcribe_with_openai(audio_path: Path, language: str) -> str:
    api_key = _get_secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    model = _get_secret("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
    prompt = _get_secret("OPENAI_TRANSCRIBE_PROMPT", DEFAULT_TRANSCRIBE_PROMPT)
    client = OpenAI(api_key=api_key)
    with tempfile.TemporaryDirectory(prefix="stt_", dir=str(audio_path.parent)) as tmp:
        work_dir = Path(tmp)
        chunks = _prepare_openai_audio_files(audio_path, work_dir)
        texts: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            with chunk.open("rb") as audio_file:
                result = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    language=language,
                    prompt=prompt,
                    response_format="text",
                )
            text = str(result).strip()
            if text:
                if len(chunks) > 1:
                    texts.append(f"[Part {index}]\n{text}")
                else:
                    texts.append(text)
        return "\n\n".join(texts).strip()


def transcribe_audio(audio_path: str | Path, language: str = "ko") -> str:
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    local_text = _transcribe_with_whisper_cpp(path, language)
    if local_text:
        return local_text

    return _transcribe_with_openai(path, language)
