from __future__ import annotations

from itertools import cycle
from pathlib import Path

from common import load_config, parse_time_list, parse_time_ranges, read_json, resolve_path, work_path, write_json


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


def build_water_like_clips(water_like, duration_sec: float, auto_insert: bool, manual_times, manual_ranges=None):
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
                'gain_db': -7,
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
                'gain_db': -7,
                'type': 'water_like_manual',
                'score': item.get('water_score', 0),
            })
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
                'gain_db': -7,
                'type': 'water_like',
                'score': item.get('water_score', 0),
            })
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
    auto_water_times = []
    if (not water_times) and (not water_ranges):
        events = main_data.get('water_events', []) or []
        # use peak times, de-duplicate, limit
        times = sorted({round(float(e.get('peak_time_sec', e.get('start_sec', 0.0))), 3) for e in events})
        filtered = []
        for t in times:
            if not filtered or abs(t - filtered[-1]) >= 0.65:
                filtered.append(t)
        auto_water_times = filtered[:12]

    water_pool = []
    if water_source == 'ref':
        water_pool = build_water_like_clips(
            ref_data.get('water_like', []),
            duration_sec,
            bool(rules.get('auto_insert_water_like', False)) and not water_times and not water_ranges,
            water_times or auto_water_times,
            water_ranges,
        )
    elif water_source == 'mechanical':
        water_pool = build_water_like_clips(
            assets_data.get('mechanical_water', []),
            duration_sec,
            False,
            water_times or auto_water_times,
            water_ranges,
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

    sfx = sorted(shutter + water_pool + extra_sfx, key=lambda x: x['start_sec'])

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
