from __future__ import annotations

import argparse
import configparser
import io
import mimetypes
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import soundfile as sf
from flask import Flask, Response, jsonify, render_template, request, send_file

from common import ROOT, read_json

CONFIG_INI_PATH = ROOT / "config.ini"
RUN_PIPELINE_PATH = ROOT / "scripts" / "run_pipeline.py"
PANEL_ROOT = ROOT / "panel"

SECTION_ORDER = [
    "global",
    "project",
    "files",
    "select",
    "insert",
    "mechanical",
    "schedule",
]

BASE_FIELDS = {
    "global": [
        {"key": "profile", "label": "單一 Profile", "type": "text", "help": "留空時使用一般模式；指定時等於固定套用同名 profile。"},
    ],
    "project": [
        {"key": "input_dir", "label": "輸入資料夾", "type": "text", "browse": "dir"},
        {"key": "work_dir", "label": "工作資料夾", "type": "text", "browse": "dir"},
        {"key": "output_dir", "label": "輸出資料夾", "type": "text", "browse": "dir"},
    ],
    "files": [
        {"key": "main_video", "label": "主影片", "type": "text", "browse": "file"},
        {"key": "ref_video", "label": "Ref 影片", "type": "text", "browse": "file"},
        {"key": "shutter_sfx", "label": "閃光音效", "type": "text", "browse": "file"},
        {"key": "moan1_audio", "label": "聲音素材 1", "type": "text", "browse": "file"},
        {"key": "moan2_audio", "label": "聲音素材 2", "type": "text", "browse": "file"},
        {"key": "sfx_audio", "label": "音效來源", "type": "text", "browse": "file"},
        {"key": "mechanical_audio", "label": "機械 / 循環音來源", "type": "text", "browse": "file"},
        {"key": "final_video", "label": "輸出檔案", "type": "text", "browse": "file"},
    ],
    "select": [
        {"key": "ambience_source", "label": "環境音來源", "type": "select", "options": ["ref", "none"]},
        {"key": "voice_source", "label": "聲音來源", "type": "select", "options": ["ref", "moan", "none"]},
        {"key": "moan_variant", "label": "聲音素材版本", "type": "select", "options": ["1", "2"]},
        {"key": "water_source", "label": "動態音效來源", "type": "select", "options": ["ref", "mechanical", "none"]},
        {"key": "enable_sfx", "label": "啟用額外音效", "type": "checkbox"},
        {"key": "enable_shutter", "label": "啟用閃光音效", "type": "checkbox"},
    ],
    "insert": [
        {"key": "voice_times", "label": "聲音時間點", "type": "textarea", "help": "例如 12.3, 00:45.0"},
        {"key": "voice_ranges", "label": "聲音時間段", "type": "textarea", "help": "例如 00:19-00:26, 37-40"},
        {"key": "water_times", "label": "動態音效時間點", "type": "textarea"},
        {"key": "water_ranges", "label": "動態音效時間段", "type": "textarea"},
        {"key": "sfx_times", "label": "音效時間點", "type": "textarea"},
        {"key": "sfx_ranges", "label": "音效時間段", "type": "textarea"},
        {"key": "shutter_times", "label": "閃光時間點", "type": "textarea"},
        {"key": "shutter_ranges", "label": "閃光時間段", "type": "textarea"},
    ],
    "mechanical": [
        {"key": "water_source_ranges", "label": "機械 / 循環音切割段", "type": "textarea"},
    ],
    "schedule": [
        {"key": "profiles", "label": "排程 Profiles", "type": "text", "help": "例如 main1, main2, main3"},
    ],
}

PROFILE_FIELDS = [
    {"key": "files.final_video", "label": "輸出檔案", "type": "text", "browse": "file"},
    {"key": "select.voice_source", "label": "聲音來源", "type": "select", "options": ["", "ref", "moan", "none"]},
    {"key": "select.moan_variant", "label": "聲音素材版本", "type": "select", "options": ["", "1", "2"]},
    {"key": "select.water_source", "label": "動態音效來源", "type": "select", "options": ["", "ref", "mechanical", "none"]},
    {"key": "select.enable_sfx", "label": "啟用額外音效", "type": "select", "options": ["", "true", "false"]},
    {"key": "select.enable_shutter", "label": "啟用閃光音效", "type": "select", "options": ["", "true", "false"]},
    {"key": "insert.voice_times", "label": "聲音時間點", "type": "textarea"},
    {"key": "insert.voice_ranges", "label": "聲音時間段", "type": "textarea"},
    {"key": "insert.water_times", "label": "動態音效時間點", "type": "textarea"},
    {"key": "insert.water_ranges", "label": "動態音效時間段", "type": "textarea"},
    {"key": "insert.sfx_times", "label": "音效時間點", "type": "textarea"},
    {"key": "insert.sfx_ranges", "label": "音效時間段", "type": "textarea"},
    {"key": "insert.shutter_times", "label": "閃光時間點", "type": "textarea"},
    {"key": "insert.shutter_ranges", "label": "閃光時間段", "type": "textarea"},
]

SECTION_TITLES = {
    "global": "全域設定",
    "project": "資料夾",
    "files": "素材路徑",
    "select": "來源選擇",
    "insert": "手動插入時間",
    "mechanical": "機械 / 循環音切割",
    "schedule": "排程輸出",
}

COMMENTS = {
    "global": [
        "# 可選：指定單一 profile（或用 run_pipeline.py --profiles）",
    ],
    "project": [],
    "files": [
        "# 主影片 / ref / 各類音源路徑",
    ],
    "select": [
        "# voice_source: ref | moan | none",
        "# water_source: ref | mechanical | none",
        "# moan_variant: 1 | 2",
    ],
    "insert": [
        "# 可填秒數或 00:00.000，逗號分隔；ranges 用 start-end",
    ],
    "mechanical": [
        "# 機械 / 循環音檔自己的時間軸，用來切出可重複使用的音效片段",
    ],
    "schedule": [
        "# 這裡列出的 profile 會在 --use-schedule 時依序輸出",
    ],
}

DEFAULTS = {
    "global": {"profile": ""},
    "project": {"input_dir": "input", "work_dir": "work", "output_dir": "output"},
    "files": {
        "main_video": "input/main.mp4",
        "ref_video": "input/ref.mp4",
        "shutter_sfx": "input/shutter/shutter.m4a",
        "moan1_audio": "input/voice1/voice1.mp3",
        "moan2_audio": "input/voice2/voice2.mp3",
        "sfx_audio": "input/sfx/sfx.mp3",
        "mechanical_audio": "input/mechanical/mechanical.mp3",
        "final_video": "output/final.mp4",
    },
    "select": {
        "ambience_source": "ref",
        "voice_source": "ref",
        "moan_variant": "1",
        "water_source": "ref",
        "enable_sfx": "false",
        "enable_shutter": "true",
    },
    "insert": {
        "voice_times": "",
        "voice_ranges": "",
        "water_times": "",
        "water_ranges": "",
        "sfx_times": "",
        "sfx_ranges": "",
        "shutter_times": "",
        "shutter_ranges": "",
    },
    "mechanical": {
        "water_source_ranges": "00:19-00:26, 00:37-00:40, 00:44-00:50, 00:58-01:10",
    },
    "schedule": {"profiles": ""},
}


def _read_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(CONFIG_INI_PATH, encoding="utf-8")
    return parser


def _normalize_value(value: Any, field_type: str) -> str:
    if field_type == "checkbox":
        if isinstance(value, str):
            return "true" if value.strip().lower() in {"1", "true", "yes", "on"} else "false"
        return "true" if bool(value) else "false"
    if value is None:
        return ""
    return str(value)


def _load_base_state(parser: configparser.ConfigParser) -> dict[str, dict[str, str]]:
    base: dict[str, dict[str, str]] = {}
    for section in SECTION_ORDER:
        section_values = dict(DEFAULTS.get(section, {}))
        if parser.has_section(section):
            for key, value in parser.items(section):
                section_values[key] = value
        base[section] = section_values
    return base


def _load_profiles(parser: configparser.ConfigParser) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for section in parser.sections():
        if not section.startswith("profile:"):
            continue
        name = section.split(":", 1)[1].strip()
        values = {key: value for key, value in parser.items(section)}
        profiles.append({"name": name, "values": values})
    return profiles


def _config_value(parser: configparser.ConfigParser, section: str, key: str, profile: str | None = None) -> str:
    if profile:
        profile_section = f"profile:{profile}"
        dotted_key = f"{section}.{key}"
        if parser.has_section(profile_section) and parser.has_option(profile_section, dotted_key):
            return parser.get(profile_section, dotted_key)
    if parser.has_section(section) and parser.has_option(section, key):
        return parser.get(section, key)
    return str(DEFAULTS.get(section, {}).get(key, ""))


def _resolve_config_path(parser: configparser.ConfigParser, section: str, key: str, profile: str | None = None) -> Path:
    raw = _config_value(parser, section, key, profile)
    path = Path(raw)
    if path.is_absolute():
        return path
    return ROOT / path


def _resolve_source_path(parser: configparser.ConfigParser, source_key: str, profile: str | None = None) -> Path:
    valid_keys = {field["key"] for field in BASE_FIELDS["files"]}
    if source_key not in valid_keys:
        raise KeyError(source_key)
    return _resolve_config_path(parser, "files", source_key, profile)


def _resolve_media_request_path(parser: configparser.ConfigParser, source_key: str, raw_path: str, profile: str | None = None) -> Path:
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        return path
    if not source_key:
        raise ValueError("缺少 source_key 或 path。")
    return _resolve_source_path(parser, source_key, profile)


def load_panel_state() -> dict[str, Any]:
    parser = _read_parser()
    return {
        "base": _load_base_state(parser),
        "profiles": _load_profiles(parser),
    }


def _render_field_line(key: str, value: str) -> str:
    return f"{key} = {value}".rstrip()


def _render_config_text(payload: dict[str, Any]) -> str:
    base = payload.get("base", {})
    profiles = payload.get("profiles", [])
    lines: list[str] = []

    for section in SECTION_ORDER:
        if lines:
            lines.append("")
        lines.append(f"[{section}]")
        for comment in COMMENTS.get(section, []):
            lines.append(comment)

        values = base.get(section, {})
        for field in BASE_FIELDS.get(section, []):
            key = field["key"]
            value = _normalize_value(values.get(key, DEFAULTS.get(section, {}).get(key, "")), field["type"])
            lines.append(_render_field_line(key, value))

    if profiles:
        lines.append("")
        lines.append("# Profiles")
        for profile in profiles:
            name = str(profile.get("name", "")).strip()
            if not name:
                continue
            lines.append("")
            lines.append(f"[profile:{name}]")
            values = profile.get("values", {}) or {}
            for field in PROFILE_FIELDS:
                key = field["key"]
                value = _normalize_value(values.get(key, ""), field["type"])
                if value == "":
                    continue
                lines.append(_render_field_line(key, value))

    return "\n".join(lines).strip() + "\n"


def save_panel_state(payload: dict[str, Any]) -> None:
    text = _render_config_text(payload)
    CONFIG_INI_PATH.write_text(text, encoding="utf-8")


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class PipelineRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._process: subprocess.Popen[str] | None = None
        self._log_lines: list[str] = []
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._exit_code: int | None = None
        self._command: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "exit_code": self._exit_code,
                "command": self._command,
                "log": "".join(self._log_lines[-400:]),
            }

    def _append(self, line: str) -> None:
        with self._lock:
            self._log_lines.append(line)
            self._log_lines = self._log_lines[-2000:]

    def start(self, mode: str, profiles: list[str] | None = None) -> tuple[bool, str]:
        with self._lock:
            if self._running:
                return False, "目前已有流程在執行中。"

            cmd = ["python", str(RUN_PIPELINE_PATH), "--ini", str(CONFIG_INI_PATH)]
            if mode == "schedule":
                cmd.append("--use-schedule")
            elif mode == "profile":
                selected = [name.strip() for name in (profiles or []) if name.strip()]
                if not selected:
                    return False, "請先選擇 profile。"
                cmd.extend(["--profiles", ",".join(selected)])

            self._running = True
            self._started_at = _iso_now()
            self._finished_at = None
            self._exit_code = None
            self._command = cmd
            self._log_lines = [f"$ {' '.join(cmd)}\n"]

        thread = threading.Thread(target=self._run_process, args=(cmd,), daemon=True)
        thread.start()
        return True, "流程已啟動。"

    def _run_process(self, cmd: list[str]) -> None:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["KM_CONFIG_INI"] = str(CONFIG_INI_PATH)

        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        with self._lock:
            self._process = process

        assert process.stdout is not None
        for line in process.stdout:
            self._append(line)

        exit_code = process.wait()
        with self._lock:
            self._running = False
            self._process = None
            self._finished_at = _iso_now()
            self._exit_code = exit_code


runner = PipelineRunner()


def _safe_profile_name(raw: str | None) -> str | None:
    name = (raw or "").strip()
    if not name:
        return None
    if any(token in name for token in ("..", "/", "\\", ":")):
        return None
    return name


def _work_dir_for_profile(profile: str | None) -> Path:
    if profile:
        return ROOT / "work" / profile
    return ROOT / "work"


def _resolve_browser_path(raw: str | None) -> Path:
    value = (raw or "").strip()
    if not value:
        return ROOT

    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path

    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path

    if resolved.is_file():
        return resolved.parent
    return resolved


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _serialize_entry(path: Path) -> dict[str, Any]:
    return {
        "name": path.name or str(path),
        "path": str(path),
        "valuePath": _display_path(path),
        "isDir": path.is_dir(),
    }


def _browser_shortcuts(current: Path) -> list[dict[str, str]]:
    shortcuts: list[dict[str, str]] = []
    candidates = [
        ("專案根目錄", ROOT),
        ("input", ROOT / "input"),
        ("output", ROOT / "output"),
        ("work", ROOT / "work"),
        (f"{current.drive or '目前磁碟'} 根目錄", Path(f"{current.drive}\\") if current.drive else current),
    ]
    seen: set[str] = set()
    for label, path in candidates:
        raw = str(path)
        if raw in seen or not path.exists():
            continue
        seen.add(raw)
        shortcuts.append({"label": label, "path": raw})
    return shortcuts


def browse_directory(path_value: str | None, mode: str) -> dict[str, Any]:
    current = _resolve_browser_path(path_value)
    if not current.exists():
        current = ROOT

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except PermissionError:
        children = []

    for child in children:
        if mode == "dir" and not child.is_dir():
            continue
        entries.append(_serialize_entry(child))

    parent = current.parent if current.parent != current else None
    return {
        "currentPath": str(current),
        "currentValuePath": _display_path(current),
        "parentPath": str(parent) if parent else None,
        "entries": entries,
        "shortcuts": _browser_shortcuts(current),
    }


def discover_analysis_targets(config_state: dict[str, Any]) -> list[dict[str, str]]:
    names = [""]
    seen = {""}

    for profile in config_state.get("profiles", []):
        name = profile.get("name", "").strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)

    work_root = ROOT / "work"
    if work_root.exists():
        for child in sorted(work_root.iterdir()):
            if child.is_dir() and child.name not in seen:
                if (child / "analysis").exists():
                    names.append(child.name)
                    seen.add(child.name)

    return [{"value": name, "label": "目前設定" if not name else name} for name in names]


def load_analysis_summary(profile: str | None) -> dict[str, Any]:
    work_dir = _work_dir_for_profile(profile)
    analysis_dir = work_dir / "analysis"
    main_data = read_json(analysis_dir / "main_analysis.json", {}) or {}
    ref_data = read_json(analysis_dir / "ref_analysis.json", {}) or {}
    assets_data = read_json(analysis_dir / "assets_analysis.json", {}) or {}
    timeline = read_json(analysis_dir / "timeline.json", {}) or {}

    tracks = timeline.get("tracks", []) or []
    track_counts = {track.get("name", "track"): len(track.get("clips", []) or []) for track in tracks}

    return {
        "profile": profile or "",
        "work_dir": str(work_dir),
        "water_events": (main_data.get("water_events") or [])[:30],
        "flash_holds": (main_data.get("flash_holds") or [])[:20],
        "shutter_candidates": (main_data.get("shutter_candidates") or [])[:20],
        "mechanical_water": (assets_data.get("mechanical_water") or [])[:20],
        "voice_candidates": (ref_data.get("voice_reactions") or [])[:20],
        "track_counts": track_counts,
    }


def _safe_audio_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path
    if not resolved.exists() or resolved.is_dir():
        return None
    return resolved


def render_waveform_svg(audio_path: Path, width: int = 860, height: int = 260) -> str:
    samples, sample_rate = sf.read(str(audio_path), always_2d=False)
    if isinstance(samples, np.ndarray) and samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        samples = np.zeros(1, dtype=np.float32)

    bucket_count = max(32, min(420, width // 2))
    chunk_size = max(1, int(np.ceil(samples.size / bucket_count)))
    peaks: list[float] = []
    for start in range(0, samples.size, chunk_size):
        chunk = samples[start:start + chunk_size]
        peaks.append(float(np.max(np.abs(chunk))) if chunk.size else 0.0)
    if not peaks:
        peaks = [0.0]

    peak_max = max(peaks) or 1.0
    norm = [peak / peak_max for peak in peaks]
    mid_y = height / 2
    usable_h = height * 0.36
    step = width / max(len(norm), 1)

    path_parts = [f"M 0 {mid_y:.2f}"]
    for idx, value in enumerate(norm):
        x = idx * step
        y = mid_y - (value * usable_h)
        path_parts.append(f"L {x:.2f} {y:.2f}")
    for idx, value in reversed(list(enumerate(norm))):
        x = idx * step
        y = mid_y + (value * usable_h)
        path_parts.append(f"L {x:.2f} {y:.2f}")
    path_parts.append("Z")

    duration = samples.size / float(sample_rate or 1)
    label = f"{audio_path.name} | {duration:.2f}s"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="waveFill" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f766e" stop-opacity="0.92"/>
      <stop offset="100%" stop-color="#155e75" stop-opacity="0.78"/>
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" rx="20" fill="#f8f5ee"/>
  <line x1="0" y1="{mid_y:.2f}" x2="{width}" y2="{mid_y:.2f}" stroke="#d2ddd8" stroke-width="1"/>
  <path d="{' '.join(path_parts)}" fill="url(#waveFill)" opacity="0.94"/>
  <text x="18" y="30" fill="#1a1f1d" font-size="18" font-family="Manrope, Noto Sans TC, sans-serif">{label}</text>
</svg>"""


def render_video_frame(profile: str | None, time_sec: float) -> bytes:
    parser = _read_parser()
    video_path = _resolve_config_path(parser, "files", "main_video", profile)
    if not video_path.exists():
        raise FileNotFoundError(f"找不到主影片：{video_path}")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"無法打開影片：{video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    target_frame = max(0, int(round(float(time_sec) * fps)))
    capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ok, frame = capture.read()
    if not ok:
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, target_frame - 2))
        ok, frame = capture.read()
    capture.release()

    if not ok or frame is None:
        raise RuntimeError("無法擷取該時間點的縮圖。")

    max_width = 960
    if frame.shape[1] > max_width:
        scale = max_width / frame.shape[1]
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise RuntimeError("縮圖編碼失敗。")
    return encoded.tobytes()


def parse_timecode(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        return float(value)

    raw = str(value or "").strip()
    if not raw:
        raise ValueError("時間不能為空。")

    if ":" not in raw:
        return float(raw)

    parts = raw.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60.0 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600.0 + float(minutes) * 60.0 + float(seconds)
    raise ValueError(f"不支援的時間格式：{raw}")


def has_stream(path: Path, stream_selector: str) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            stream_selector,
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return bool(result.stdout.strip())


def _parse_ffprobe_rate(raw: str) -> float:
    text = (raw or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return 0.0
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            num = float(numerator)
            den = float(denominator)
            return num / den if den else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def probe_media_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"找不到媒體檔案：{path}")

    duration_sec = 0.0
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    raw_duration = (result.stdout or "").strip()
    if raw_duration:
        try:
            duration_sec = max(0.0, float(raw_duration))
        except ValueError:
            duration_sec = 0.0

    has_video = has_stream(path, "v:0")
    has_audio = has_stream(path, "a:0")
    media_kind = "video" if has_video else "audio" if has_audio else "unknown"
    video_fps = 0.0
    if has_video:
        fps_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=avg_frame_rate,r_frame_rate",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        rate_lines = [line.strip() for line in (fps_result.stdout or "").splitlines() if line.strip()]
        parsed_rates = [_parse_ffprobe_rate(line) for line in rate_lines]
        video_fps = max((rate for rate in parsed_rates if rate > 0), default=0.0)
    return {
        "path": str(path),
        "value_path": _display_path(path),
        "duration_sec": round(duration_sec, 3),
        "has_video": has_video,
        "has_audio": has_audio,
        "media_kind": media_kind,
        "video_fps": round(video_fps, 3) if video_fps > 0 else 0.0,
        "name": path.name,
    }


def export_segment(
    source_path: Path,
    start_sec: float,
    end_sec: float,
    output_kind: str,
    output_dir: Path,
    output_name: str,
) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"找不到來源檔案：{source_path}")
    if start_sec < 0 or end_sec <= start_sec:
        raise ValueError("擷取時間範圍不正確。")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name

    if output_kind == "video":
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
        if not has_stream(source_path, "v:0"):
            raise ValueError("這個來源沒有影片軌，不能輸出影片片段。")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-to",
            f"{end_sec:.3f}",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
        ]
        if has_stream(source_path, "a:0"):
            cmd.extend(["-map", "0:a:0?"])
        cmd.extend([
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            str(output_path),
        ])
    else:
        suffix = output_path.suffix.lower()
        if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".flac"}:
            output_path = output_path.with_suffix(".wav")
            suffix = ".wav"
        if not has_stream(source_path, "a:0"):
            raise ValueError("這個來源沒有音訊軌，不能輸出音訊片段。")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-to",
            f"{end_sec:.3f}",
            "-i",
            str(source_path),
            "-vn",
        ]
        if suffix == ".wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif suffix == ".mp3":
            cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
        elif suffix in {".m4a", ".aac"}:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        elif suffix == ".flac":
            cmd.extend(["-c:a", "flac"])
        cmd.append(str(output_path))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr.splitlines()[-1] if stderr else "FFmpeg 擷取失敗。")

    return output_path


def list_exported_segments(output_dir: Path) -> list[dict[str, Any]]:
    if not output_dir.exists() or not output_dir.is_dir():
        return []

    items: list[dict[str, Any]] = []
    for child in sorted(output_dir.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        if not child.is_file():
            continue
        stat = child.stat()
        items.append(
            {
                "name": child.name,
                "path": str(child),
                "value_path": _display_path(child),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items[:120]


def open_directory_in_explorer(path: Path) -> None:
    target = path if path.is_dir() else path.parent
    target.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "startfile"):
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    subprocess.Popen(["explorer", str(target)])


app = Flask(
    __name__,
    template_folder=str(PANEL_ROOT / "templates"),
    static_folder=str(PANEL_ROOT / "static"),
)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def _asset_version() -> str:
    targets = [
        PANEL_ROOT / "static" / "panel.js",
        PANEL_ROOT / "static" / "panel.css",
        PANEL_ROOT / "templates" / "index.html",
        CONFIG_INI_PATH,
    ]
    mtimes = []
    for path in targets:
        try:
            mtimes.append(int(path.stat().st_mtime))
        except OSError:
            continue
    return str(max(mtimes) if mtimes else int(datetime.now().timestamp()))


@app.after_request
def add_no_cache_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/")
def index() -> str:
    panel_meta = {
        "sectionOrder": SECTION_ORDER,
        "sectionTitles": SECTION_TITLES,
        "baseFields": BASE_FIELDS,
        "profileFields": PROFILE_FIELDS,
    }
    return render_template(
        "index.html",
        panel_meta=panel_meta,
        config_path=str(CONFIG_INI_PATH),
        asset_version=_asset_version(),
    )


@app.get("/api/state")
def api_state() -> Any:
    state = load_panel_state()
    return jsonify(
        {
            "config": state,
            "status": runner.snapshot(),
            "analysisTargets": discover_analysis_targets(state),
        }
    )


@app.post("/api/config")
def api_save_config() -> Any:
    payload = request.get_json(force=True) or {}
    save_panel_state(payload)
    state = load_panel_state()
    return jsonify(
        {
            "ok": True,
            "message": "設定已儲存。",
            "config": state,
            "analysisTargets": discover_analysis_targets(state),
        }
    )


@app.post("/api/run")
def api_run() -> Any:
    payload = request.get_json(force=True) or {}
    mode = str(payload.get("mode", "current"))
    profiles = payload.get("profiles") or []
    clean_profiles = []
    for item in profiles:
        name = _safe_profile_name(str(item))
        if name:
            clean_profiles.append(name)

    ok, message = runner.start(mode, clean_profiles)
    code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message, "status": runner.snapshot()}), code


@app.get("/api/status")
def api_status() -> Any:
    return jsonify(runner.snapshot())


@app.get("/api/analysis")
def api_analysis() -> Any:
    profile = _safe_profile_name(request.args.get("profile"))
    return jsonify(load_analysis_summary(profile))


@app.get("/api/fs")
def api_fs() -> Any:
    mode = str(request.args.get("mode", "file")).lower()
    if mode not in {"file", "dir"}:
        mode = "file"
    path_value = request.args.get("path")
    return jsonify(browse_directory(path_value, mode))


@app.get("/api/preview/frame")
def api_preview_frame() -> Any:
    profile = _safe_profile_name(request.args.get("profile"))
    try:
        time_sec = float(request.args.get("time", "0") or 0.0)
        payload = render_video_frame(profile, time_sec)
    except FileNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception as exc:  # pragma: no cover - defensive API surface
        return jsonify({"message": str(exc)}), 422
    return send_file(io.BytesIO(payload), mimetype="image/jpeg", download_name="preview.jpg")


@app.get("/api/preview/waveform")
def api_preview_waveform() -> Any:
    audio_path = _safe_audio_path(request.args.get("path"))
    if audio_path is None:
        return jsonify({"message": "找不到音訊檔案。"}), 404
    svg = render_waveform_svg(audio_path)
    return Response(svg, mimetype="image/svg+xml")


@app.get("/api/media/info")
def api_media_info() -> Any:
    parser = _read_parser()
    profile = _safe_profile_name(request.args.get("profile"))
    source_key = str(request.args.get("source_key", "")).strip()
    raw_path = str(request.args.get("path", "")).strip()

    try:
        path = _resolve_media_request_path(parser, source_key, raw_path, profile)
        info = probe_media_info(path)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except KeyError:
        return jsonify({"message": f"不支援的來源：{source_key}"}), 400
    except FileNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception as exc:  # pragma: no cover - defensive API surface
        return jsonify({"message": str(exc)}), 422

    info["profile"] = profile or ""
    info["source_key"] = source_key
    return jsonify(info)


@app.get("/api/media/file")
def api_media_file() -> Any:
    parser = _read_parser()
    profile = _safe_profile_name(request.args.get("profile"))
    source_key = str(request.args.get("source_key", "")).strip()
    raw_path = str(request.args.get("path", "")).strip()

    try:
        path = _resolve_media_request_path(parser, source_key, raw_path, profile)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"找不到媒體檔案：{path}")
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except KeyError:
        return jsonify({"message": f"不支援的來源：{source_key}"}), 400
    except FileNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404

    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return send_file(path, conditional=True, download_name=path.name, mimetype=mime_type)


@app.post("/api/export/segment")
def api_export_segment() -> Any:
    payload = request.get_json(force=True) or {}
    source_raw = str(payload.get("source_path", "")).strip()
    output_dir_raw = str(payload.get("output_dir", "")).strip() or "output/clips"
    output_name = str(payload.get("output_name", "")).strip() or "clip"
    output_kind = str(payload.get("output_kind", "video")).strip().lower()

    if output_kind not in {"video", "audio"}:
        return jsonify({"message": "輸出種類只能是 video 或 audio。"}), 400

    try:
        start_sec = parse_timecode(payload.get("start_time", ""))
        end_sec = parse_timecode(payload.get("end_time", ""))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    if not source_raw:
        return jsonify({"message": "請先指定來源檔案。"}), 400

    source_path = Path(source_raw)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    output_dir = Path(output_dir_raw)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    try:
        out_path = export_segment(source_path, start_sec, end_sec, output_kind, output_dir, output_name)
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"message": str(exc)}), 422

    return jsonify(
        {
            "ok": True,
            "message": "片段已輸出。",
            "output_path": str(out_path),
            "output_value_path": _display_path(out_path),
            "start_sec": round(start_sec, 3),
            "end_sec": round(end_sec, 3),
            "output_kind": output_kind,
        }
    )


@app.get("/api/export/list")
def api_export_list() -> Any:
    output_dir_raw = str(request.args.get("dir", "")).strip() or "output/clips"
    output_dir = Path(output_dir_raw)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    return jsonify(
        {
            "output_dir": str(output_dir),
            "output_value_dir": _display_path(output_dir),
            "items": list_exported_segments(output_dir),
        }
    )


@app.post("/api/open-folder")
def api_open_folder() -> Any:
    payload = request.get_json(force=True) or {}
    raw_path = str(payload.get("path", "")).strip()
    if not raw_path:
        return jsonify({"message": "缺少資料夾路徑。"}), 400

    target = Path(raw_path)
    if not target.is_absolute():
        target = ROOT / target

    try:
        open_directory_in_explorer(target)
    except Exception as exc:  # pragma: no cover - OS integration
        return jsonify({"message": str(exc)}), 422

    return jsonify({"ok": True, "message": "已開啟資料夾。", "path": str(target)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5010)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
