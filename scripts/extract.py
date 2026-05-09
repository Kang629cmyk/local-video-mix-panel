from __future__ import annotations

from pathlib import Path

from common import ensure_dir, ffprobe_duration, load_config, resolve_path, run_cmd, work_path, write_json


def extract_audio_if_present(video_path: Path, out_wav: Path, label: str) -> bool:
    probe_cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=index',
        '-of', 'csv=p=0',
        str(video_path),
    ]

    import subprocess
    result = subprocess.run(probe_cmd, capture_output=True, text=True, check=False)
    has_audio = bool(result.stdout.strip())
    if not has_audio:
        print(f'{label} 不含音轨，跳过音频抽取: {video_path}')
        return False

    run_cmd(['ffmpeg', '-y', '-i', str(video_path), '-vn', '-ac', '1', '-ar', '16000', str(out_wav)])
    return True


def main() -> None:
    cfg = load_config()
    files = cfg['files']
    select = cfg.get('select', {})

    main_video = resolve_path(cfg, files['main_video'])
    ref_video_value = files.get('ref_video')
    ambience_source = str(select.get('ambience_source', 'ref'))
    voice_source = str(select.get('voice_source', 'ref'))
    water_source = str(select.get('water_source', 'ref'))
    needs_ref = ambience_source == 'ref' or voice_source == 'ref' or water_source == 'ref'
    ref_video = resolve_path(cfg, ref_video_value) if ref_video_value else None

    work_audio_main = work_path(cfg, 'audio_main')
    work_audio_ref = work_path(cfg, 'audio_ref')
    work_frames = work_path(cfg, 'frames')
    analysis_dir = work_path(cfg, 'analysis')

    for d in [work_audio_main, work_audio_ref, work_frames, analysis_dir]:
        ensure_dir(d)

    main_wav = work_audio_main / 'main.wav'
    ref_wav = work_audio_ref / 'ref.wav'

    if not main_video.exists():
        raise FileNotFoundError(f'缺少主影片: {main_video}')
    if needs_ref and (ref_video is None or not ref_video.exists()):
        raise FileNotFoundError(f'缺少素材影片(ref): {ref_video_value}')

    main_has_audio = extract_audio_if_present(main_video, main_wav, '主影片')
    ref_has_audio = extract_audio_if_present(ref_video, ref_wav, '素材影片') if ref_video and ref_video.exists() else False

    frame_fps = str(cfg['analysis']['frame_sample_fps'])
    run_cmd([
        'ffmpeg', '-y', '-i', str(main_video), '-vf', f'fps={frame_fps}', str(work_frames / 'frame_%05d.jpg')
    ])

    metadata = {
        'main_video': str(main_video),
        'ref_video': str(ref_video) if ref_video else None,
        'main_duration_sec': ffprobe_duration(main_video),
        'ref_duration_sec': ffprobe_duration(ref_video) if ref_video and ref_video.exists() else None,
        'main_audio_wav': str(main_wav) if main_has_audio else None,
        'ref_audio_wav': str(ref_wav) if ref_has_audio else None,
        'main_has_audio': main_has_audio,
        'ref_has_audio': ref_has_audio,
    }
    write_json(analysis_dir / 'media_metadata.json', metadata)
    print('完成 extract')


if __name__ == '__main__':
    main()
