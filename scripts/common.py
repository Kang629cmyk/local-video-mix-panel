from __future__ import annotations

import json
import math
import os
import subprocess
import configparser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / 'config.yaml'
INI_PATH = ROOT / 'config.ini'


def _deep_merge(base: MutableMapping[str, Any], override: Mapping[str, Any]) -> MutableMapping[str, Any]:
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            _deep_merge(base[key], value)  # type: ignore[index]
        else:
            base[key] = value
    return base


def _split_csv(value: str) -> List[str]:
    parts = []
    for raw in value.replace(';', ',').split(','):
        item = raw.strip()
        if item:
            parts.append(item)
    return parts


def _parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if s.lower() in {'true', 'yes', 'on'}:
        return True
    if s.lower() in {'false', 'no', 'off'}:
        return False
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _ini_to_dict(ini_path: Path) -> Dict[str, Any]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ini_path, encoding='utf-8')
    result: Dict[str, Any] = {}

    def set_dotted(target: MutableMapping[str, Any], dotted_key: str, value: Any) -> None:
        parts = [p for p in dotted_key.split('.') if p]
        if not parts:
            return
        cur: MutableMapping[str, Any] = target
        for p in parts[:-1]:
            nxt = cur.get(p)
            if not isinstance(nxt, MutableMapping):
                nxt = {}
                cur[p] = nxt
            cur = nxt  # type: ignore[assignment]
        cur[parts[-1]] = value

    for section in parser.sections():
        section_map: Dict[str, Any] = {}
        for key, raw in parser.items(section):
            if raw is None:
                continue
            val = raw.strip()
            # Keep "time-like" specs as string; parse later where used.
            if (
                key.endswith('_times')
                or key.endswith('_ranges')
                or key.endswith('_source_ranges')
                or key.endswith('_times_sec')
                or key.endswith('_ranges_sec')
            ):
                set_dotted(section_map, key, val)
            elif ',' in val or ';' in val:
                set_dotted(section_map, key, [_parse_scalar(x) for x in _split_csv(val)])
            else:
                set_dotted(section_map, key, _parse_scalar(val))
        result[section] = section_map
    return result


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}

    ini_path = Path(os.environ.get('KM_CONFIG_INI', str(INI_PATH)))
    if ini_path.exists():
        ini_cfg = _ini_to_dict(ini_path)
        profile = os.environ.get('KM_PROFILE')
        if not profile:
            profile = str(ini_cfg.get('global', {}).get('profile', '')).strip() or None
        if profile:
            prof_key = f'profile:{profile}'
            prof_over = ini_cfg.get(prof_key, {})
            ini_cfg = {k: v for k, v in ini_cfg.items() if not k.startswith('profile:')}
            if prof_over:
                ini_cfg['_profile_overrides'] = prof_over
        _deep_merge(cfg, ini_cfg)
        if cfg.get('_profile_overrides'):
            _deep_merge(cfg, cfg.pop('_profile_overrides'))

    profile = os.environ.get('KM_PROFILE') or None
    if profile:
        project = cfg.setdefault('project', {})
        if isinstance(project, MutableMapping) and str(project.get('work_dir', 'work')) == 'work':
            project['work_dir'] = f'work/{profile}'
    return cfg


def get_ini_schedule_profiles(cfg: Mapping[str, Any]) -> List[str]:
    schedule = cfg.get('schedule', {}) if isinstance(cfg.get('schedule', {}), Mapping) else {}
    raw = schedule.get('profiles', '')
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if not isinstance(raw, str):
        return []
    return _split_csv(raw)


def _parse_hhmmss(token: str) -> float:
    s = token.strip()
    if not s:
        raise ValueError('empty time token')
    if ':' not in s:
        return float(s)
    parts = s.split(':')
    if len(parts) == 2:
        mm, ss = parts
        return float(mm) * 60.0 + float(ss)
    if len(parts) == 3:
        hh, mm, ss = parts
        return float(hh) * 3600.0 + float(mm) * 60.0 + float(ss)
    raise ValueError(f'bad time token: {token}')


def parse_time_list(spec: Any) -> List[float]:
    if spec is None:
        return []
    if isinstance(spec, list):
        out: List[float] = []
        for item in spec:
            if item is None:
                continue
            out.append(float(item))
        return out
    if not isinstance(spec, str):
        return [float(spec)]
    tokens = _split_csv(spec)
    out = []
    for t in tokens:
        out.append(_parse_hhmmss(t))
    return out


def parse_time_ranges(spec: Any) -> List[Tuple[float, float]]:
    if spec is None:
        return []
    if isinstance(spec, list):
        out = []
        for item in spec:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append((float(item[0]), float(item[1])))
        return out
    if not isinstance(spec, str):
        return []
    tokens = _split_csv(spec)
    out: List[Tuple[float, float]] = []
    for tok in tokens:
        if '-' not in tok:
            t = _parse_hhmmss(tok)
            out.append((t, t))
            continue
        a, b = [x.strip() for x in tok.split('-', 1)]
        start = _parse_hhmmss(a)
        end = _parse_hhmmss(b)
        if end < start:
            start, end = end, start
        out.append((start, end))
    return out


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_path(cfg: Mapping[str, Any], value: str | Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return ROOT / p


def project_dir(cfg: Mapping[str, Any], key: str, default: str) -> Path:
    project = cfg.get('project', {}) if isinstance(cfg.get('project', {}), Mapping) else {}
    raw = project.get(key, default)
    return resolve_path(cfg, str(raw))


def input_root(cfg: Mapping[str, Any]) -> Path:
    return project_dir(cfg, 'input_dir', 'input')


def work_root(cfg: Mapping[str, Any]) -> Path:
    return project_dir(cfg, 'work_dir', 'work')


def output_root(cfg: Mapping[str, Any]) -> Path:
    return project_dir(cfg, 'output_dir', 'output')


def work_path(cfg: Mapping[str, Any], *parts: str) -> Path:
    return work_root(cfg).joinpath(*parts)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_cmd(cmd: List[str]) -> None:
    print('>>', ' '.join(cmd))
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', str(path)
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def db_to_gain(db: float) -> float:
    return 10 ** (db / 20.0)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def sec_to_ms(sec: float) -> int:
    return max(0, int(sec * 1000))


def rms(samples) -> float:
    if len(samples) == 0:
        return 0.0
    return math.sqrt(float((samples.astype('float64') ** 2).mean()))
