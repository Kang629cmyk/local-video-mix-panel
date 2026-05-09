from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from common import (
    ensure_dir,
    load_config,
    parse_time_ranges,
    resolve_path,
    run_cmd,
    work_path,
    write_json,
)


def _export_slice_ffmpeg(src: Path, start_sec: float, end_sec: float, out_wav: Path, sample_rate: int = 48000) -> None:
    ensure_dir(out_wav.parent)
    run_cmd([
        'ffmpeg',
        '-y',
        '-ss',
        f'{start_sec:.3f}',
        '-to',
        f'{end_sec:.3f}',
        '-i',
        str(src),
        '-vn',
        '-ac',
        '1',
        '-ar',
        str(sample_rate),
        str(out_wav),
    ])


def _segment_by_silence(src: AudioSegment, min_silence_ms: int = 220, keep_silence_ms: int = 60):
    if len(src) <= 0:
        return []
    thresh = src.dBFS - 16
    chunks = detect_nonsilent(src, min_silence_len=min_silence_ms, silence_thresh=thresh)
    segs = []
    for start_ms, end_ms in chunks:
        s = max(0, start_ms - keep_silence_ms)
        e = min(len(src), end_ms + keep_silence_ms)
        if e - s < 180:
            continue
        segs.append((s, e))
    return segs


def _export_segment(src: AudioSegment, start_ms: int, end_ms: int, out_wav: Path) -> float:
    ensure_dir(out_wav.parent)
    clip = src[start_ms:end_ms]
    clip.export(out_wav, format='wav')
    return float(len(clip) / 1000.0)


def _analyze_simple_audio(audio_path: Path, out_dir: Path, prefix: str, limit: int = 40):
    if not audio_path.exists():
        return []
    src = AudioSegment.from_file(audio_path)
    segs = _segment_by_silence(src)
    segs = segs[:limit]
    items = []
    for idx, (s_ms, e_ms) in enumerate(segs):
        out = out_dir / f'{prefix}_{idx:03d}.wav'
        dur = _export_segment(src, s_ms, e_ms, out)
        items.append({
            'path': str(out),
            'duration_sec': round(dur, 3),
            'src_start_sec': round(s_ms / 1000.0, 3),
            'src_end_sec': round(e_ms / 1000.0, 3),
        })
    return items


def main() -> None:
    cfg = load_config()
    files = cfg.get('files', {})
    analysis_dir = work_path(cfg, 'analysis')
    seg_dir = work_path(cfg, 'segments')
    ensure_dir(analysis_dir)
    ensure_dir(seg_dir)

    mix_sr = int(cfg.get('mix', {}).get('sample_rate', 48000))

    mechanical_audio = resolve_path(cfg, files.get('mechanical_audio', '')) if files.get('mechanical_audio') else None
    water_source_ranges = parse_time_ranges(cfg.get('mechanical', {}).get('water_source_ranges'))

    mechanical_water = []
    if mechanical_audio and mechanical_audio.exists() and water_source_ranges:
        out_dir = seg_dir / 'mechanical_water'
        ensure_dir(out_dir)
        for idx, (start, end) in enumerate(water_source_ranges, start=1):
            out = out_dir / f'water_{idx:03d}.wav'
            _export_slice_ffmpeg(mechanical_audio, start, end, out, sample_rate=mix_sr)
            mechanical_water.append({
                'path': str(out),
                'duration_sec': round(float(end - start), 3),
                'src_start_sec': round(float(start), 3),
                'src_end_sec': round(float(end), 3),
                'src': str(mechanical_audio),
            })

    moan1_audio = resolve_path(cfg, files.get('moan1_audio', '')) if files.get('moan1_audio') else None
    moan2_audio = resolve_path(cfg, files.get('moan2_audio', '')) if files.get('moan2_audio') else None
    sfx_audio = resolve_path(cfg, files.get('sfx_audio', '')) if files.get('sfx_audio') else None

    moan1_segments = _analyze_simple_audio(moan1_audio, seg_dir / 'moan1', 'moan1') if moan1_audio else []
    moan2_segments = _analyze_simple_audio(moan2_audio, seg_dir / 'moan2', 'moan2') if moan2_audio else []
    sfx_segments = _analyze_simple_audio(sfx_audio, seg_dir / 'sfx', 'sfx') if sfx_audio else []

    data = {
        'mechanical_water': mechanical_water,
        'moan1_segments': moan1_segments,
        'moan2_segments': moan2_segments,
        'sfx_segments': sfx_segments,
    }
    write_json(analysis_dir / 'assets_analysis.json', data)
    print('完成 analyze_assets')


if __name__ == '__main__':
    main()
