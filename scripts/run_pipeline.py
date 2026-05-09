from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from common import ROOT, get_ini_schedule_profiles, load_config

SCRIPTS = [
    'extract.py',
    'analyze_main_video.py',
    'analyze_ref_audio.py',
    'analyze_assets.py',
    'build_timeline.py',
    'render_mix.py',
]


def _run_scripts(env: dict, profile: str | None) -> None:
    for script in SCRIPTS:
        path = ROOT / 'scripts' / script
        title = f'{script} ({profile})' if profile else script
        print(f'==== RUN {title} ====')
        subprocess.run(['python', str(path)], check=True, env=env)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ini', default=os.environ.get('KM_CONFIG_INI', str(ROOT / 'config.ini')))
    parser.add_argument('--profiles', default='')
    parser.add_argument('--use-schedule', action='store_true', help='使用 config.ini [schedule] profiles')
    args = parser.parse_args()

    base_env = os.environ.copy()
    base_env['KM_CONFIG_INI'] = str(Path(args.ini))
    os.environ['KM_CONFIG_INI'] = base_env['KM_CONFIG_INI']

    if args.profiles.strip():
        profiles = [p.strip() for p in args.profiles.replace(';', ',').split(',') if p.strip()]
    elif args.use_schedule:
        cfg = load_config()
        profiles = get_ini_schedule_profiles(cfg)
    else:
        profiles = []

    if not profiles:
        _run_scripts(base_env, None)
        print('全部流程完成')
        return

    for prof in profiles:
        env = dict(base_env)
        env['KM_PROFILE'] = prof
        _run_scripts(env, prof)
    print('全部排程完成')


if __name__ == '__main__':
    main()
