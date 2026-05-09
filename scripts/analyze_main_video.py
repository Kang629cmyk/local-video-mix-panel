from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import whisper
from scenedetect import AdaptiveDetector, SceneManager, open_video

from common import ffprobe_duration, load_config, resolve_path, work_path, write_json


def detect_scenes(video_path: Path, threshold: float):
    video = open_video(str(video_path))
    manager = SceneManager()
    manager.add_detector(AdaptiveDetector(adaptive_threshold=threshold))
    manager.detect_scenes(video)
    scene_list = manager.get_scene_list()
    result = []
    for idx, (start, end) in enumerate(scene_list):
        result.append({
            'id': idx,
            'start_sec': start.get_seconds(),
            'end_sec': end.get_seconds(),
        })
    return result


def analyze_visual_energy(video_path: Path):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    sample_step = max(1, int(round(fps / 8.0)))
    prev_gray = None
    points = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % sample_step != 0:
            idx += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        white_ratio = float(np.mean(gray >= 235))
        edges = cv2.Canny(gray, 80, 160)
        edge_density = float(np.mean(edges > 0))
        bright_edge_ratio = float(np.mean((edges > 0) & (gray >= 210)))
        motion = 0.0
        flash_edge = 0.0

        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            motion = float(np.mean(diff))
            flash_edge = float(np.mean((gray >= 235) & (prev_gray < 200)))

        line_count = 0
        mean_line_len = 0.0
        if edge_density >= 0.015:
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180.0,
                threshold=45,
                minLineLength=max(18, int(min(gray.shape[:2]) * 0.06)),
                maxLineGap=8,
            )
            if lines is not None and len(lines) > 0:
                line_count = int(len(lines))
                lengths = []
                for x1, y1, x2, y2 in lines.reshape(-1, 4):
                    lengths.append(float(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5))
                mean_line_len = float(np.mean(lengths)) if lengths else 0.0

        # Water-like spray: bright thin streaks + edges + local motion.
        water_score = (
            bright_edge_ratio * 3.2
            + edge_density * 1.6
            + min(line_count / 220.0, 1.0) * 0.9
            + min(motion / 22.0, 1.0) * 0.6
        )

        prev_gray = gray
        points.append({
            'time_sec': idx / fps,
            'brightness': brightness,
            'motion': motion,
            'white_ratio': white_ratio,
            'flash_edge': flash_edge,
            'edge_density': round(edge_density, 5),
            'bright_edge_ratio': round(bright_edge_ratio, 5),
            'line_count': line_count,
            'mean_line_len': round(mean_line_len, 2),
            'water_score': round(float(water_score), 5),
        })
        idx += 1
    cap.release()
    return points


def detect_flash_events(visual_points):
    if len(visual_points) < 3:
        return []

    flashes = []
    for i in range(1, len(visual_points) - 1):
        prev_p = visual_points[i - 1]
        cur_p = visual_points[i]
        next_p = visual_points[i + 1]

        rise = cur_p['brightness'] - prev_p['brightness']
        decay = cur_p['brightness'] - next_p['brightness']
        white_boost = cur_p['white_ratio'] - prev_p.get('white_ratio', 0.0)
        flash_edge = cur_p.get('flash_edge', 0.0)
        motion_penalty = cur_p['motion'] * 0.05

        is_flash_peak = rise > 18 and decay > 8
        enough_white = cur_p['white_ratio'] > 0.08 or white_boost > 0.04 or flash_edge > 0.03

        if is_flash_peak and enough_white:
            score = rise * 1.2 + decay * 0.8 + white_boost * 220 + flash_edge * 260 - motion_penalty
            flashes.append({
                'time_sec': round(float(cur_p['time_sec']), 3),
                'score': round(float(score), 3),
                'brightness_rise': round(float(rise), 3),
                'brightness_decay': round(float(decay), 3),
                'white_ratio': round(float(cur_p['white_ratio']), 4),
                'white_boost': round(float(white_boost), 4),
                'flash_edge': round(float(flash_edge), 4),
            })
    return flashes


def group_flash_bursts(flash_events, burst_gap_sec: float = 0.42):
    if not flash_events:
        return []

    sorted_events = sorted(flash_events, key=lambda x: x['time_sec'])
    bursts = []
    current = [sorted_events[0]]

    for event in sorted_events[1:]:
        if event['time_sec'] - current[-1]['time_sec'] <= burst_gap_sec:
            current.append(event)
        else:
            bursts.append(current)
            current = [event]
    bursts.append(current)

    result = []
    for idx, burst in enumerate(bursts):
        times = [x['time_sec'] for x in burst]
        count = len(burst)
        duration = times[-1] - times[0] if count > 1 else 0.0
        avg_interval = (duration / (count - 1)) if count > 1 else None
        max_score = max(x['score'] for x in burst)
        avg_score = sum(x['score'] for x in burst) / count

        if count <= 2:
            shutter_style = 'short_burst'
        elif avg_interval is not None and avg_interval <= 0.16:
            shutter_style = 'long_burst'
        elif count >= 4:
            shutter_style = 'long_burst'
        else:
            shutter_style = 'short_burst'

        result.append({
            'id': idx,
            'start_sec': round(times[0], 3),
            'end_sec': round(times[-1], 3),
            'count': count,
            'times_sec': times,
            'duration_sec': round(float(duration), 3),
            'avg_interval_sec': round(float(avg_interval), 3) if avg_interval is not None else None,
            'max_score': round(float(max_score), 3),
            'avg_score': round(float(avg_score), 3),
            'shutter_style': shutter_style,
        })
    return result


def detect_flash_hold_events(visual_points, hold_white_ratio: float = 0.22, min_len_sec: float = 0.25):
    holds = []
    current = None
    for p in visual_points:
        is_hold = (p.get('white_ratio', 0.0) >= hold_white_ratio) and (p.get('brightness', 0.0) >= 215)
        if is_hold:
            if current is None:
                current = {'start_sec': float(p['time_sec']), 'end_sec': float(p['time_sec']), 'max_white_ratio': float(p['white_ratio'])}
            else:
                current['end_sec'] = float(p['time_sec'])
                current['max_white_ratio'] = max(current['max_white_ratio'], float(p['white_ratio']))
        else:
            if current is not None:
                if current['end_sec'] - current['start_sec'] >= min_len_sec:
                    holds.append(current)
                current = None
    if current is not None and current['end_sec'] - current['start_sec'] >= min_len_sec:
        holds.append(current)
    for idx, h in enumerate(holds):
        h['id'] = idx
        h['duration_sec'] = round(float(h['end_sec'] - h['start_sec']), 3)
        h['start_sec'] = round(float(h['start_sec']), 3)
        h['end_sec'] = round(float(h['end_sec']), 3)
        h['max_white_ratio'] = round(float(h['max_white_ratio']), 4)
    return holds


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return (a_start <= b_end) and (b_start <= a_end)


def detect_shutter_candidates(visual_points, limit: int):
    flash_events = detect_flash_events(visual_points)
    bursts = group_flash_bursts(flash_events)
    holds = detect_flash_hold_events(visual_points)

    used_hold_ids = set()
    for b in bursts:
        for h in holds:
            if _overlap(float(b['start_sec']), float(b['end_sec']), float(h['start_sec']), float(h['end_sec'])):
                used_hold_ids.add(h['id'])
                b['shutter_style'] = 'long_hold'
                b['start_sec'] = round(float(min(float(b['start_sec']), float(h['start_sec']))), 3)
                b['end_sec'] = round(float(max(float(b['end_sec']), float(h['end_sec']))), 3)
                b['duration_sec'] = round(float(b['end_sec'] - b['start_sec']), 3)

    for h in holds:
        if h['id'] in used_hold_ids:
            continue
        bursts.append({
            'id': f"hold_{h['id']}",
            'start_sec': h['start_sec'],
            'end_sec': h['end_sec'],
            'count': 0,
            'times_sec': [h['start_sec']],
            'duration_sec': h['duration_sec'],
            'avg_interval_sec': None,
            'max_score': 0.0,
            'avg_score': 0.0,
            'shutter_style': 'long_hold',
            'hold_max_white_ratio': h['max_white_ratio'],
        })

    ranked = sorted(bursts, key=lambda x: (x['count'], x['max_score'], x['avg_score']), reverse=True)
    selected = ranked[:limit]
    return sorted(selected, key=lambda x: float(x['start_sec'])), flash_events, holds


def detect_water_events(visual_points, min_len_sec: float = 0.25, gap_sec: float = 0.35):
    if not visual_points:
        return []
    scores = np.array([float(p.get('water_score', 0.0)) for p in visual_points], dtype=np.float32)
    thresh = float(max(0.08, np.percentile(scores, 97)))
    events = []
    cur = None
    for p in visual_points:
        t = float(p['time_sec'])
        score = float(p.get('water_score', 0.0))
        white_ratio = float(p.get('white_ratio', 0.0))
        is_candidate = (score >= thresh) and (white_ratio <= 0.62)
        if is_candidate:
            if cur is None:
                cur = {'start_sec': t, 'end_sec': t, 'peak_time_sec': t, 'peak_score': score, 'count': 1}
            else:
                if t - cur['end_sec'] <= gap_sec:
                    cur['end_sec'] = t
                    cur['count'] += 1
                    if score > cur['peak_score']:
                        cur['peak_score'] = score
                        cur['peak_time_sec'] = t
                else:
                    events.append(cur)
                    cur = {'start_sec': t, 'end_sec': t, 'peak_time_sec': t, 'peak_score': score, 'count': 1}
        else:
            if cur is not None:
                events.append(cur)
                cur = None
    if cur is not None:
        events.append(cur)

    out = []
    for idx, e in enumerate(events):
        if e['end_sec'] - e['start_sec'] < min_len_sec:
            continue
        out.append({
            'id': idx,
            'start_sec': round(float(e['start_sec']), 3),
            'end_sec': round(float(e['end_sec']), 3),
            'duration_sec': round(float(e['end_sec'] - e['start_sec']), 3),
            'peak_time_sec': round(float(e['peak_time_sec']), 3),
            'peak_score': round(float(e['peak_score']), 5),
            'sample_count': int(e['count']),
            'threshold': round(thresh, 5),
        })
    return out


def detect_motion_events(visual_points, min_len_sec: float = 0.18, gap_sec: float = 0.32):
    if not visual_points:
        return []

    motions = np.array([float(p.get('motion', 0.0)) for p in visual_points], dtype=np.float32)
    if float(np.max(motions)) <= 0.0:
        return []

    thresh = float(max(8.0, np.percentile(motions, 92)))
    events = []
    cur = None

    for p in visual_points:
        t = float(p['time_sec'])
        motion = float(p.get('motion', 0.0))
        white_ratio = float(p.get('white_ratio', 0.0))
        water_score = float(p.get('water_score', 0.0))
        is_candidate = motion >= thresh and white_ratio <= 0.55

        if is_candidate:
            sample = {
                'time_sec': t,
                'motion': motion,
                'edge_density': float(p.get('edge_density', 0.0)),
                'water_score': water_score,
            }
            if cur is None:
                cur = {
                    'start_sec': t,
                    'end_sec': t,
                    'peak_time_sec': t,
                    'peak_motion': motion,
                    'samples': [sample],
                }
            elif t - cur['end_sec'] <= gap_sec:
                cur['end_sec'] = t
                cur['samples'].append(sample)
                if motion > cur['peak_motion']:
                    cur['peak_motion'] = motion
                    cur['peak_time_sec'] = t
            else:
                events.append(cur)
                cur = {
                    'start_sec': t,
                    'end_sec': t,
                    'peak_time_sec': t,
                    'peak_motion': motion,
                    'samples': [sample],
                }
        elif cur is not None:
            events.append(cur)
            cur = None

    if cur is not None:
        events.append(cur)

    out = []
    for idx, e in enumerate(events):
        duration = float(e['end_sec'] - e['start_sec'])
        if duration < min_len_sec:
            continue

        samples = e['samples']
        sample_count = len(samples)
        pulse_count = 1
        for i in range(1, max(1, sample_count - 1)):
            prev_m = samples[i - 1]['motion']
            cur_m = samples[i]['motion']
            next_m = samples[i + 1]['motion']
            if cur_m >= prev_m and cur_m >= next_m and cur_m >= thresh:
                pulse_count += 1
        pulse_rate_hz = pulse_count / max(duration, 0.18)
        avg_motion = sum(s['motion'] for s in samples) / sample_count
        avg_edge = sum(s['edge_density'] for s in samples) / sample_count
        avg_water = sum(s['water_score'] for s in samples) / sample_count
        motion_amplitude = min(float(e['peak_motion']) / max(thresh, 1.0), 3.0)

        out.append({
            'id': idx,
            'start_sec': round(float(e['start_sec']), 3),
            'end_sec': round(float(e['end_sec']), 3),
            'duration_sec': round(duration, 3),
            'peak_time_sec': round(float(e['peak_time_sec']), 3),
            'peak_motion': round(float(e['peak_motion']), 3),
            'avg_motion': round(float(avg_motion), 3),
            'avg_edge_density': round(float(avg_edge), 5),
            'avg_water_score': round(float(avg_water), 5),
            'pulse_count': int(pulse_count),
            'pulse_rate_hz': round(float(pulse_rate_hz), 3),
            'motion_amplitude': round(float(motion_amplitude), 3),
            'threshold': round(thresh, 3),
        })
    return out


def transcribe_main(audio_path: Path):
    model = whisper.load_model('base')
    result = model.transcribe(str(audio_path), fp16=False)
    segments = []
    for seg in result.get('segments', []):
        segments.append({
            'start_sec': float(seg['start']),
            'end_sec': float(seg['end']),
            'text': seg['text'].strip(),
        })
    return segments


def main() -> None:
    cfg = load_config()
    files = cfg['files']
    analysis_dir = work_path(cfg, 'analysis')
    main_video = resolve_path(cfg, files['main_video'])
    main_audio = work_path(cfg, 'audio_main', 'main.wav')

    duration = ffprobe_duration(main_video)
    scenes = detect_scenes(main_video, cfg['analysis']['scene_threshold'])
    visual_points = analyze_visual_energy(main_video)
    shutter_candidates, flash_events, flash_holds = detect_shutter_candidates(visual_points, cfg['analysis']['max_shutter_candidates'])
    water_events = detect_water_events(visual_points)
    motion_events = detect_motion_events(visual_points)
    dialogue_segments = transcribe_main(main_audio) if main_audio.exists() else []

    data = {
        'duration_sec': duration,
        'scenes': scenes,
        'visual_points': visual_points,
        'flash_events': flash_events,
        'flash_holds': flash_holds,
        'shutter_candidates': shutter_candidates,
        'water_events': water_events,
        'motion_events': motion_events,
        'dialogue_segments': dialogue_segments,
    }
    write_json(analysis_dir / 'main_analysis.json', data)
    print('完成 analyze_main_video')


if __name__ == '__main__':
    main()
