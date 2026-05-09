from __future__ import annotations

from pathlib import Path

from moviepy.editor import AudioFileClip, CompositeAudioClip, VideoFileClip

from common import db_to_gain, ensure_dir, load_config, read_json, resolve_path, work_path


def make_clip(clip_info):
    clip = AudioFileClip(clip_info['src'])
    offset = clip_info.get('offset_sec', 0.0)
    duration = clip_info.get('duration_sec')
    if duration:
        end = min(clip.duration, offset + duration)
        clip = clip.subclip(offset, end)

    gain = db_to_gain(clip_info.get('gain_db', 0.0))
    fade_in = 0.005 if 'shutter' in clip_info.get('type', '') else 0.01
    fade_out = 0.03 if 'shutter' in clip_info.get('type', '') else 0.04
    clip = clip.volumex(gain).audio_fadein(fade_in).audio_fadeout(fade_out).set_start(clip_info['start_sec'])
    return clip


def main() -> None:
    cfg = load_config()
    files = cfg['files']
    timeline = read_json(work_path(cfg, 'analysis', 'timeline.json'), {})
    main_video_path = resolve_path(cfg, files['main_video'])
    final_video_path = resolve_path(cfg, files['final_video'])
    temp_audio_path = work_path(cfg, 'mix', 'temp-audio.m4a')
    ensure_dir(final_video_path.parent)
    ensure_dir(temp_audio_path.parent)

    if final_video_path.exists():
        raise FileExistsError(f'輸出檔案已存在，為避免覆蓋已停止: {final_video_path}')

    video = VideoFileClip(str(main_video_path))
    audio_layers = []

    if video.audio is not None:
        audio_layers.append(video.audio)

    for track in timeline.get('tracks', []):
        for clip_info in track.get('clips', []):
            src = Path(clip_info['src'])
            if src.exists():
                audio_layers.append(make_clip(clip_info))

    if not audio_layers:
        final = video
    else:
        mixed = CompositeAudioClip(audio_layers)
        final = video.set_audio(mixed)

    final.write_videofile(
        str(final_video_path),
        codec='libx264',
        audio_codec='aac',
        temp_audiofile=str(temp_audio_path),
        remove_temp=True,
        threads=4,
    )
    print(f'完成 render_mix -> {final_video_path}')


if __name__ == '__main__':
    main()
