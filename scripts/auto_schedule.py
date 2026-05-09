from __future__ import annotations

import configparser
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIST = ROOT / "auto_schedule.txt"
BASE_INI = ROOT / "config.ini"
EXAMPLE_INI = ROOT / "config.example.ini"
GENERATED_DIR = ROOT / "work" / "auto_schedule"
GENERATED_INI = GENERATED_DIR / "generated_config.ini"


COMMENT_PREFIXES = ("#", ";", "//")
SUFFIX_KEYS = {"suffix", "output_suffix", "後綴", "輸出後綴"}


def split_items(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]


def read_schedule_list(path: Path) -> tuple[str, list[str]]:
    suffix = "_final"
    files: list[str] = []

    if not path.exists():
        raise FileNotFoundError(f"找不到清單檔: {path}")

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(COMMENT_PREFIXES):
            continue

        if "=" in line:
            key, value = [part.strip() for part in line.split("=", 1)]
            if key in SUFFIX_KEYS:
                suffix = value or suffix
                continue
            if key.lower() in {"file", "files", "filename", "filenames", "影片", "檔名"}:
                files.extend(split_items(value))
                continue

        files.extend(split_items(line))

    if not files:
        raise ValueError("清單裡沒有影片檔名。")
    if not suffix:
        raise ValueError("輸出後綴不可空白。")

    return suffix, files


def read_base_ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str

    ini_path = BASE_INI if BASE_INI.exists() else EXAMPLE_INI
    if not ini_path.exists():
        raise FileNotFoundError(f"找不到 config.ini 或 config.example.ini: {BASE_INI}")

    parser.read(ini_path, encoding="utf-8")
    return parser


def project_path(parser: configparser.ConfigParser, key: str, default: str) -> Path:
    raw = parser.get("project", key, fallback=default)
    path = Path(raw)
    if path.is_absolute():
        return path
    return ROOT / path


def normalize_input_name(name: str) -> str:
    path = Path(name.strip().strip('"'))
    if path.suffix:
        return path.as_posix()
    return path.with_suffix(".mp4").as_posix()


def make_profile_name(stem: str, used: set[str]) -> str:
    base = re.sub(r"[^0-9A-Za-z_.-]+", "_", stem).strip("._-") or "video"
    profile = base
    idx = 2
    while profile in used:
        profile = f"{base}_{idx}"
        idx += 1
    used.add(profile)
    return profile


def build_generated_ini(
    parser: configparser.ConfigParser,
    suffix: str,
    file_names: list[str],
) -> tuple[Path, list[Path]]:
    for section in list(parser.sections()):
        if section == "schedule" or section.startswith("profile:"):
            parser.remove_section(section)

    input_dir = project_path(parser, "input_dir", "input")
    output_dir = project_path(parser, "output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    profiles: list[str] = []
    output_paths: list[Path] = []
    used_profiles: set[str] = set()

    parser.add_section("schedule")

    for raw_name in file_names:
        input_name = normalize_input_name(raw_name)
        input_path = Path(input_name)
        resolved_input = input_path if input_path.is_absolute() else input_dir / input_path.name
        if not resolved_input.exists():
            raise FileNotFoundError(f"找不到輸入影片: {resolved_input}")

        stem = input_path.stem
        profile = make_profile_name(stem, used_profiles)
        profiles.append(profile)

        output_name = f"{stem}{suffix}.mp4"
        output_path = output_dir / output_name
        output_paths.append(output_path)

        section = f"profile:{profile}"
        parser.add_section(section)
        parser.set(section, "files.main_video", f"input/{resolved_input.name}")
        parser.set(section, "files.final_video", f"output/{output_name}")

    existing_outputs = [path for path in output_paths if path.exists()]
    if existing_outputs:
        lines = "\n".join(f"  - {path}" for path in existing_outputs)
        raise FileExistsError(f"以下輸出檔已存在，為避免覆蓋已停止:\n{lines}")

    parser.set("schedule", "profiles", ", ".join(profiles))

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    with GENERATED_INI.open("w", encoding="utf-8") as f:
        parser.write(f)

    return GENERATED_INI, output_paths


def main() -> int:
    list_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIST
    if not list_path.is_absolute():
        list_path = ROOT / list_path

    suffix, file_names = read_schedule_list(list_path)
    parser = read_base_ini()
    generated_ini, output_paths = build_generated_ini(parser, suffix, file_names)

    print(f"已產生排程設定: {generated_ini}")
    print("預計輸出:")
    for path in output_paths:
        print(f"  - {path}")
    print()

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_pipeline.py"),
        "--ini",
        str(generated_ini),
        "--use-schedule",
    ]
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"錯誤: {exc}", file=sys.stderr)
        raise SystemExit(1)
