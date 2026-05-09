from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import whisper
from pydub import AudioSegment

from common import clamp, load_config, sec_to_ms, work_path, write_json


def merge_short_gaps(segments, max_gap_sec: float = 0.2, min_len_sec: float = 0.25):
    if not segments:
        return []
    merged = [list(segments[0])]
    for start, end in segments[1:]:
        prev = merged[-1]
        if start - prev[1] <= max_gap_sec:
            prev[1] = end
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged if e - s >= min_len_sec]


def detect_speech_segments_from_whisper(ref_wav: Path):
    model = whisper.load_model('base')
    transcript = model.transcribe(str(ref_wav), fp16=False)
    raw_segments = []
    for seg in transcript.get('segments', []):
        start = float(seg['start'])
        end = float(seg['end'])
        if end > start:
            raw_segments.append((start, end))
    return merge_short_gaps(raw_segments), transcript


def build_non_speech_segments(duration_sec: float, speech_segments, min_len: float):
    result = []
    cursor = 0.0
    for start, end in speech_segments:
        if start - cursor >= min_len:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if duration_sec - cursor >= min_len:
        result.append((cursor, duration_sec))
    return result


def export_segment(src: AudioSegment, start: float, end: float, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clip = src[sec_to_ms(start):sec_to_ms(end)]
    clip.export(out_path, format='wav')


def analyze_effect_candidates(ref_wav: Path, speech_segments, max_sec: float):
    audio, sr = sf.read(str(ref_wav))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    duration_sec = len(audio) / sr

    mask = np.ones(len(audio), dtype=bool)
    for start, end in speech_segments:
        s = int(max(0, start) * sr)
        e = int(min(duration_sec, end) * sr)
        mask[s:e] = False

    window_sec = 0.35
    hop_sec = 0.12
    window = int(window_sec * sr)
    hop = int(hop_sec * sr)
    candidates = []

    for start_idx in range(0, max(1, len(audio) - window), hop):
        end_idx = min(len(audio), start_idx + window)
        segment = audio[start_idx:end_idx]
        if len(segment) < int(0.18 * sr):
            continue
        if not mask[start_idx:end_idx].mean() > 0.8:
            continue

        duration = (end_idx - start_idx) / sr
        if duration > max_sec:
            continue

        rms = float(np.sqrt(np.mean(segment ** 2)))
        if rms < 0.01:
            continue

        spec = np.fft.rfft(segment)
        mag = np.abs(spec) + 1e-9
        freqs = np.fft.rfftfreq(len(segment), d=1.0 / sr)
        centroid = float((freqs * mag).sum() / mag.sum())
        high_ratio = float(mag[freqs >= 2500].sum() / mag.sum())
        zero_cross = float(((segment[:-1] * segment[1:]) < 0).mean()) if len(segment) > 1 else 0.0
        water_score = rms * 2.5 + high_ratio * 1.7 + zero_cross * 1.2 + min(centroid / 6000.0, 1.0)

        candidates.append({
            'start_sec': round(start_idx / sr, 3),
            'end_sec': round(end_idx / sr, 3),
            'duration_sec': round(duration, 3),
            'rms': round(rms, 5),
            'centroid_hz': round(centroid, 1),
            'high_ratio': round(high_ratio, 4),
            'zero_cross': round(zero_cross, 4),
            'water_score': round(water_score, 4),
        })

    candidates.sort(key=lambda x: x['water_score'], reverse=True)
    selected = []
    for cand in candidates:
        if all(abs(cand['start_sec'] - prev['start_sec']) >= 0.3 for prev in selected):
            selected.append(cand)
        if len(selected) >= 12:
            break
    return sorted(selected, key=lambda x: x['start_sec'])


def main() -> None:
    cfg = load_config()
    ref_wav = work_path(cfg, 'audio_ref', 'ref.wav')
    analysis_dir = work_path(cfg, 'analysis')
    seg_dir = work_path(cfg, 'segments')

    select = cfg.get('select', {})
    ambience_source = str(select.get('ambience_source', 'ref'))
    voice_source = str(select.get('voice_source', 'ref'))
    water_source = str(select.get('water_source', 'ref'))
    needs_ref = ambience_source == 'ref' or voice_source == 'ref' or water_source == 'ref'

    if not ref_wav.exists() or not needs_ref:
        write_json(analysis_dir / 'ref_analysis.json', {
            'duration_sec': 0.0,
            'speech_segments': [],
            'ambience_segments': [],
            'voice_reactions': [],
            'effects': [],
            'water_like': [],
            'transcript_text': '',
            'skipped': True,
        })
        print('跳过 analyze_ref_audio (不需要 ref)')
        return
    src = AudioSegment.from_wav(ref_wav)
    duration_sec = len(src) / 1000.0

    speech_segments, transcript = detect_speech_segments_from_whisper(ref_wav)
    ambience_segments = build_non_speech_segments(duration_sec, speech_segments, cfg['analysis']['ambience_min_sec'])

    voice_reactions = []
    for idx, seg in enumerate(transcript.get('segments', [])):
        start = float(seg['start'])
        end = float(seg['end'])
        text = seg['text'].strip()
        dur = end - start
        if 0.2 <= dur <= cfg['analysis']['voice_reaction_max_sec'] and len(text) <= 20:
            out = seg_dir / f'voice_reaction_{idx:03d}.wav'
            export_segment(src, start, end, out)
            voice_reactions.append({
                'path': str(out),
                'start_sec': start,
                'end_sec': end,
                'duration_sec': dur,
                'text': text,
            })

    ambience = []
    for idx, (start, end) in enumerate(ambience_segments):
        out = seg_dir / f'ambience_{idx:03d}.wav'
        export_segment(src, start, end, out)
        ambience.append({
            'path': str(out),
            'start_sec': start,
            'end_sec': end,
            'duration_sec': end - start,
        })

    effects = []
    for idx, (start, end) in enumerate(speech_segments):
        dur = end - start
        if dur <= clamp(cfg['analysis']['effect_max_sec'], 0.3, 2.5):
            out = seg_dir / f'effect_like_{idx:03d}.wav'
            export_segment(src, start, end, out)
            effects.append({
                'path': str(out),
                'start_sec': start,
                'end_sec': end,
                'duration_sec': dur,
            })

    water_like = []
    for idx, cand in enumerate(analyze_effect_candidates(ref_wav, speech_segments, cfg['analysis']['effect_max_sec'])):
        out = seg_dir / f'water_like_{idx:03d}.wav'
        export_segment(src, cand['start_sec'], cand['end_sec'], out)
        water_like.append({
            'path': str(out),
            **cand,
        })

    data = {
        'duration_sec': duration_sec,
        'speech_segments': [{'start_sec': s, 'end_sec': e} for s, e in speech_segments],
        'ambience_segments': ambience,
        'voice_reactions': voice_reactions,
        'effects': effects,
        'water_like': water_like,
        'transcript_text': transcript.get('text', '').strip(),
    }
    write_json(analysis_dir / 'ref_analysis.json', data)
    print('完成 analyze_ref_audio')


if __name__ == '__main__':
    main()
