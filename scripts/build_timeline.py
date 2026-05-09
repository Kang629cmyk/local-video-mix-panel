from __future__ import annotations

from itertools import cycle
from pathlib import Path

from common import clamp, load_config, parse_time_list, parse_time_ranges, read_json, resolve_path, work_path, write_json


def build_ambience_track(duration_sec: float, ambience_segments, gain_db: float):
    clips = []
    if not ambience_segments:
        return clips
    t = 0.0
    pool = cycle(ambience_segments)
    while t < duration_sec:
        seg = next(pool)
        dur = min(seg['duration_sec'], duration_sec - t)
        clips.append({
            'src': seg['path'],
            'start_sec': t,
            'offset_sec': 0.0,
            'duration_sec': dur,
            'gain_db': gain_db,
            'type': 'ambience',
        })
        t += max(1.0, dur - 0.8)
    return clips


def split_voice_reactions_by_length(voice_reactions):
    short_items = []
    long_items = []
    for item in voice_reactions or []:
        if item.get('duration_sec', 0) <= 1.5:
            short_items.append(item)
        else:
            long_items.append(item)
    return short_items, long_items


def filter_by_names(items, approved_files):
    approved_set = set(approved_files or [])
    if not approved_set:
        return items
    return [item for item in items if Path(item['path']).name in approved_set]


def build_voice_track(dialogue_segments, voice_reactions, gain_db: float, approved_files, insert_times, mode='by_length'):
    clips = []
    if not voice_reactions:
        return clips

    short_items, long_items = split_voice_reactions_by_length(voice_reactions)
    if mode == 'by_length':
        source_items = filter_by_names(long_items, approved_files) or filter_by_names(voice_reactions, approved_files)
    else:
        source_items = filter_by_names(voice_reactions, approved_files)

    if insert_times:
        for idx, t in enumerate(insert_times):
            if not source_items:
                break
            reaction = source_items[idx % len(source_items)]
            clips.append({
                'src': reaction['path'],
                'start_sec': float(t),
                'offset_sec': 0.0,
                'duration_sec': reaction['duration_sec'],
                'gain_db': gain_db,
                'type': 'voice_reaction_manual',
                'text': reaction.get('text', ''),
            })
        return clips

    if not dialogue_segments:
        return clips

    idx = 0
    for seg in dialogue_segments:
        if idx >= len(source_items):
            break
        insert_time = max(0.0, seg['start_sec'] - 0.15)
        reaction = source_items[idx]
        clips.append({
            'src': reaction['path'],
            'start_sec': insert_time,
            'offset_sec': 0.0,
            'duration_sec': reaction['duration_sec'],
            'gain_db': gain_db,
            'type': 'voice_reaction',
            'text': reaction.get('text', ''),
        })
        idx += 1
    return clips


def build_voice_track_ranges(voice_reactions, gain_db: float, approved_files, insert_ranges):
    clips = []
    if not voice_reactions or not insert_ranges:
        return clips
    source_items = filter_by_names(voice_reactions, approved_files)
    for idx, (start, end) in enumerate(insert_ranges):
        if not source_items:
            break
        reaction = source_items[idx % len(source_items)]
        max_dur = max(0.0, float(end) - float(start))
        dur = reaction.get('duration_sec', 0.0)
        if max_dur > 0:
            dur = min(float(dur), max_dur)
        clips.append({
            'src': reaction['path'],
            'start_sec': float(start),
            'offset_sec': 0.0,
            'duration_sec': float(dur),
            'gain_db': gain_db,
            'type': 'voice_reaction_range',
            'text': reaction.get('text', ''),
        })
    return clips


def build_shutter_clips(shutter_candidates, shutter_path: Path, shutter_gain_db: float, manual_times, manual_ranges, auto_insert: bool):
    clips = []
    if not shutter_path.exists():
        return clips

    if auto_insert:
        for burst in shutter_candidates:
            style = burst.get('shutter_style', 'short_burst')
            times = burst.get('times_sec', []) or [burst.get('start_sec', 0.0)]
            if style in {'long_burst', 'long_hold'}:
                clips.append({
                    'src': str(shutter_path),
                    'start_sec': float(burst['start_sec']),
                    'offset_sec': 0.0,
                    'duration_sec': min(0.9, max(0.28, float(burst.get('duration_sec', 0.0)) + 0.18)),
                    'gain_db': shutter_gain_db,
                    'type': 'shutter_auto_long' if style == 'long_burst' else 'shutter_auto_hold',
                    'score': burst.get('max_score', 0),
                    'count': burst.get('count', len(times)),
                })
            else:
                for t in times:
                    clips.append({
                        'src': str(shutter_path),
                        'start_sec': float(t),
                        'offset_sec': 0.0,
                        'duration_sec': 0.18,
                        'gain_db': shutter_gain_db,
                        'type': 'shutter_auto_short',
                        'score': burst.get('max_score', 0),
                        'count': burst.get('count', len(times)),
                    })

    for t in manual_times:
        clips.append({
            'src': str(shutter_path),
            'start_sec': float(t),
            'offset_sec': 0.0,
            'duration_sec': 0.18,
            'gain_db': shutter_gain_db,
            'type': 'shutter_manual',
        })

    for start, end in manual_ranges or []:
        dur = max(0.18, min(0.9, float(end) - float(start))) if float(end) > float(start) else 0.18
        clips.append({
            'src': str(shutter_path),
            'start_sec': float(start),
            'offset_sec': 0.0,
            'duration_sec': float(dur),
            'gain_db': shutter_gain_db,
            'type': 'shutter_manual_range',
        })
    return clips


def build_water_from_pool(voice_reactions, approved_files, manual_times):
    clips = []
    short_items, _ = split_voice_reactions_by_length(voice_reactions)
    source_items = filter_by_names(short_items, approved_files) or filter_by_names(voice_reactions, approved_files)
    for idx, t in enumerate(manual_times or []):
        if not source_items:
            break
        item = source_items[idx % len(source_items)]
        clips.append({
            'src': item['path'],
            'start_sec': float(t),
            'offset_sec': 0.0,
            'duration_sec': item['duration_sec'],
            'gain_db': -7,
            'type': 'water_sfx_manual',
        })
    return clips


def _event_overlap(left, right, pad_sec: float = 0.0) -> bool:
    left_start = float(left.get('start_sec', left.get('peak_time_sec', 0.0))) - pad_sec
    left_end = float(left.get('end_sec', left.get('peak_time_sec', left_start))) + pad_sec
    right_start = float(right.get('start_sec', right.get('peak_time_sec', 0.0))) - pad_sec
    right_end = float(right.get('end_sec', right.get('peak_time_sec', right_start))) + pad_sec
    return left_start <= right_end and right_start <= left_end


def _event_pulse_rate(event) -> float:
    if event.get('pulse_rate_hz') is not None:
        return float(event.get('pulse_rate_hz') or 0.0)
    duration = max(float(event.get('duration_sec', 0.0) or 0.0), 0.18)
    return float(event.get('sample_count', 1) or 1) / duration


def _event_amplitude(event, key: str, fallback: float = 1.0) -> float:
    if event.get('motion_amplitude') is not None:
        return float(event.get('motion_amplitude') or fallback)
    peak = float(event.get(key, 0.0) or 0.0)
    threshold = float(event.get('threshold', 0.0) or 0.0)
    if threshold > 0:
        return clamp(peak / threshold, 0.4, 3.0)
    return fallback


def _segment_energy(item) -> float:
    return float(item.get('energy_score', item.get('water_score', item.get('rms', 0.0))) or 0.0)


def _pick_segment_for_event(items, event, idx: int, mode: str):
    if not items:
        return None
    if not any(('centroid_hz' in item or 'energy_score' in item or 'water_score' in item) for item in items):
        return items[idx % len(items)]

    pulse_rate = clamp(_event_pulse_rate(event), 0.0, 12.0)
    amplitude = _event_amplitude(event, 'peak_motion' if mode == 'motion' else 'peak_score')
    target_centroid = 900.0 + pulse_rate * 420.0 + min(amplitude, 2.5) * 420.0
    target_energy = 0.6 + min(amplitude, 2.4) * 0.55

    def score(item):
        centroid = float(item.get('centroid_hz', target_centroid) or target_centroid)
        energy = _segment_energy(item)
        duration = float(item.get('duration_sec', 0.0) or 0.0)
        duration_target = max(0.25, float(event.get('duration_sec', 0.35) or 0.35))
        return (
            abs((centroid - target_centroid) / 6500.0)
            + abs((energy - target_energy) / 2.4)
            + abs((duration - duration_target) / 8.0)
        )

    ranked = sorted(items, key=score)
    return ranked[idx % min(3, len(ranked))]


def _auto_event_clip(item, event, duration_sec: float, gain_db: float, clip_type: str, idx: int):
    item_dur = float(item.get('duration_sec', 0.0) or 0.0)
    event_dur = float(event.get('duration_sec', 0.0) or 0.0)
    dur = min(item_dur, max(0.22, event_dur + 0.12)) if item_dur > 0 else max(0.22, event_dur)
    start = min(max(0.0, float(event.get('start_sec', event.get('peak_time_sec', 0.0)) or 0.0)), max(0.0, duration_sec - dur))
    amp = _event_amplitude(event, 'peak_motion' if 'motion' in clip_type else 'peak_score')
    gain = gain_db + clamp((amp - 1.0) * 1.8, -2.5, 3.5)
    return {
        'src': item['path'],
        'start_sec': start,
        'offset_sec': 0.0,
        'duration_sec': dur,
        'gain_db': round(float(gain), 2),
        'type': clip_type,
        'score': event.get('peak_motion', event.get('peak_score', 0)),
        'pulse_rate_hz': event.get('pulse_rate_hz'),
        'match_index': idx,
    }


def build_water_like_clips(water_like, duration_sec: float, auto_insert: bool, manual_times, manual_ranges=None, auto_events=None, gain_db: float = -7.0):
    clips = []
    if not water_like:
        return clips

    if manual_ranges:
        for idx, (start, end) in enumerate(manual_ranges):
            item = water_like[idx % len(water_like)]
            max_dur = max(0.0, float(end) - float(start))
            dur = float(item['duration_sec'])
            if max_dur > 0:
                dur = min(dur, max_dur)
            clips.append({
                'src': item['path'],
                'start_sec': min(max(0.0, float(start)), max(0.0, duration_sec - dur)),
                'offset_sec': 0.0,
                'duration_sec': dur,
                'gain_db': gain_db,
                'type': 'water_like_range',
                'score': item.get('water_score', 0),
            })
        return clips

    if manual_times:
        for idx, t in enumerate(manual_times):
            item = water_like[idx % len(water_like)]
            clips.append({
                'src': item['path'],
                'start_sec': min(max(0.0, float(t)), max(0.0, duration_sec - item['duration_sec'])),
                'offset_sec': 0.0,
                'duration_sec': item['duration_sec'],
                'gain_db': gain_db,
                'type': 'water_like_manual',
                'score': item.get('water_score', 0),
            })
        return clips

    if auto_events:
        filtered = []
        for event in sorted(auto_events, key=lambda e: float(e.get('peak_time_sec', e.get('start_sec', 0.0)))):
            if not filtered or float(event.get('peak_time_sec', event.get('start_sec', 0.0))) - float(filtered[-1].get('peak_time_sec', filtered[-1].get('start_sec', 0.0))) >= 0.65:
                filtered.append(event)
        for idx, event in enumerate(filtered[:12]):
            item = _pick_segment_for_event(water_like, event, idx, 'water')
            if item:
                clips.append(_auto_event_clip(item, event, duration_sec, gain_db, 'water_like_auto_event', idx))
        return clips

    if auto_insert:
        water_pool = water_like[: min(4, len(water_like))]
        step = max(8.0, duration_sec / (len(water_pool) + 1))
        for idx, item in enumerate(water_pool, start=1):
            clips.append({
                'src': item['path'],
                'start_sec': min(duration_sec - item['duration_sec'], step * idx),
                'offset_sec': 0.0,
                'duration_sec': item['duration_sec'],
                'gain_db': gain_db,
                'type': 'water_like',
                'score': item.get('water_score', 0),
            })
    return clips


def build_motion_mechanical_clips(mechanical_segments, motion_events, duration_sec: float, gain_db: float):
    clips = []
    if not mechanical_segments or not motion_events:
        return clips

    for idx, event in enumerate(sorted(motion_events, key=lambda e: float(e.get('peak_time_sec', e.get('start_sec', 0.0))))[:14]):
        item = _pick_segment_for_event(mechanical_segments, event, idx, 'motion')
        if item:
            clips.append(_auto_event_clip(item, event, duration_sec, gain_db, 'mechanical_motion_auto', idx))
    return clips


def build_sfx_clips(sfx_segments, duration_sec: float, gain_db: float, manual_times, manual_ranges=None, auto_times=None):
    clips = []
    if not sfx_segments:
        return clips

    if manual_ranges:
        for idx, (start, end) in enumerate(manual_ranges):
            item = sfx_segments[idx % len(sfx_segments)]
            max_dur = max(0.0, float(end) - float(start))
            dur = float(item.get('duration_sec', 0.0))
            if max_dur > 0:
                dur = min(dur, max_dur)
            clips.append({
                'src': item['path'],
                'start_sec': min(max(0.0, float(start)), max(0.0, duration_sec - dur)),
                'offset_sec': 0.0,
                'duration_sec': dur,
                'gain_db': gain_db,
                'type': 'sfx_range',
            })
        return clips

    times = manual_times or auto_times or []
    for idx, t in enumerate(times):
        item = sfx_segments[idx % len(sfx_segments)]
        clips.append({
            'src': item['path'],
            'start_sec': min(max(0.0, float(t)), max(0.0, duration_sec - item.get('duration_sec', 0.0))),
            'offset_sec': 0.0,
            'duration_sec': float(item.get('duration_sec', 0.0)),
            'gain_db': gain_db,
            'type': 'sfx',
        })
    return clips


def main() -> None:
    cfg = load_config()
    analysis_dir = work_path(cfg, 'analysis')
    main_data = read_json(analysis_dir / 'main_analysis.json', {})
    ref_data = read_json(analysis_dir / 'ref_analysis.json', {})
    assets_data = read_json(analysis_dir / 'assets_analysis.json', {})
    rules = cfg.get('rules', {})
    select = cfg.get('select', {})
    insert = cfg.get('insert', {})

    duration_sec = main_data.get('duration_sec', 0.0)

    ambience_source = str(select.get('ambience_source', 'ref'))
    voice_source = str(select.get('voice_source', 'ref'))
    water_source = str(select.get('water_source', 'ref'))
    enable_sfx = bool(select.get('enable_sfx', False))
    enable_shutter = bool(select.get('enable_shutter', True))
    enable_motion_mechanical = bool(select.get('enable_motion_mechanical', rules.get('auto_insert_motion_mechanical', True)))

    ambience_segments = ref_data.get('ambience_segments', []) if ambience_source == 'ref' else []
    ambience = build_ambience_track(duration_sec, ambience_segments, cfg['mix']['ambience_gain_db'])

    moan_variant = int(select.get('moan_variant', 1) or 1)
    moan_segments = assets_data.get('moan1_segments', []) if moan_variant == 1 else assets_data.get('moan2_segments', [])
    voice_pool = []
    if voice_source == 'ref':
        voice_pool = ref_data.get('voice_reactions', [])
    elif voice_source == 'moan':
        voice_pool = moan_segments

    voice_times = parse_time_list(insert.get('voice_times') or rules.get('insert_voice_reaction_times_sec'))
    voice_ranges = parse_time_ranges(insert.get('voice_ranges'))
    voice = []
    if voice_pool:
        approved_voice = rules.get('approved_voice_reactions', []) if voice_source == 'ref' else []
        voice += build_voice_track_ranges(voice_pool, cfg['mix']['voice_gain_db'], approved_voice, voice_ranges)
        voice += build_voice_track(
            main_data.get('dialogue_segments', []),
            voice_pool,
            cfg['mix']['voice_gain_db'],
            approved_voice,
            voice_times,
            rules.get('voice_reaction_mode', 'by_length'),
        )
    shutter = []
    shutter_src = cfg.get('files', {}).get('shutter_sfx')
    if shutter_src:
        shutter = build_shutter_clips(
            main_data.get('shutter_candidates', []),
            resolve_path(cfg, shutter_src),
            cfg['mix']['shutter_gain_db'],
            parse_time_list(insert.get('shutter_times') or rules.get('shutter_times_sec')),
            parse_time_ranges(insert.get('shutter_ranges')),
            enable_shutter and bool(rules.get('auto_insert_shutter', True)),
        )

    water_times = parse_time_list(insert.get('water_times') or rules.get('water_like_times_sec') or rules.get('water_sfx_times_sec'))
    water_ranges = parse_time_ranges(insert.get('water_ranges'))
    auto_water_events = []
    if (not water_times) and (not water_ranges):
        events = main_data.get('water_events', []) or []
        auto_water_events = sorted(events, key=lambda e: float(e.get('peak_time_sec', e.get('start_sec', 0.0))))[:12]

    water_pool = []
    if water_source == 'ref':
        water_pool = build_water_like_clips(
            ref_data.get('water_like', []),
            duration_sec,
            bool(rules.get('auto_insert_water_like', False)) and not water_times and not water_ranges,
            water_times,
            water_ranges,
            auto_water_events,
            cfg['mix'].get('water_gain_db', -7),
        )
    elif water_source == 'mechanical':
        water_pool = build_water_like_clips(
            assets_data.get('mechanical_water', []),
            duration_sec,
            False,
            water_times,
            water_ranges,
            auto_water_events,
            cfg['mix'].get('water_gain_db', -7),
        )

    water_events = main_data.get('water_events', []) or []
    motion_events = main_data.get('motion_events', []) or []
    motion_events = [event for event in motion_events if not any(_event_overlap(event, water, 0.35) for water in water_events)]
    motion_mechanical = []
    if enable_motion_mechanical:
        motion_mechanical = build_motion_mechanical_clips(
            assets_data.get('mechanical_water', []),
            motion_events,
            duration_sec,
            cfg['mix'].get('mechanical_gain_db', cfg['mix'].get('sfx_gain_db', -8) - 1),
        )

    sfx_segments = assets_data.get('sfx_segments', []) if enable_sfx else []
    sfx_times = parse_time_list(insert.get('sfx_times'))
    sfx_ranges = parse_time_ranges(insert.get('sfx_ranges'))
    auto_sfx_times = []
    if enable_sfx and not sfx_times and not sfx_ranges:
        scenes = main_data.get('scenes', []) or []
        auto_sfx_times = [float(s['start_sec']) for s in scenes[1:8] if float(s.get('start_sec', 0)) > 0.2]

    extra_sfx = build_sfx_clips(
        sfx_segments,
        duration_sec,
        cfg['mix'].get('sfx_gain_db', -8),
        sfx_times,
        sfx_ranges,
        auto_sfx_times,
    )

    sfx = sorted(shutter + water_pool + motion_mechanical + extra_sfx, key=lambda x: x['start_sec'])

    timeline = {
        'duration_sec': duration_sec,
        'tracks': [
            {'name': 'ambience', 'clips': ambience},
            {'name': 'voice', 'clips': voice},
            {'name': 'sfx', 'clips': sfx},
        ]
    }
    write_json(analysis_dir / 'timeline.json', timeline)
    print('完成 build_timeline')


if __name__ == '__main__':
    main()
