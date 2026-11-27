"""Install the field account's periodic starred-evidence reconciler on macOS."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--station', type=Path, required=True)
    parser.add_argument('--field-volume', type=Path, required=True)
    args = parser.parse_args()
    station, volume = args.station.resolve(), args.field_volume.resolve()
    if not (volume / 'uap-lab/starred-objects.json').is_file():
        parser.error('The field volume must contain the station star catalog')
    label = 'ai.starpeople.starred-archive'
    agent = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
    args_list = [station / 'venv/bin/python', station / 'capture-station/starred_archive.py',
                 '--data', volume / 'uap-lab', '--private', station / 'capture-station/private/internet-archive',
                 '--state', volume / 'archive-tags/starred-bundles']
    config = dict(Label=label, StartInterval=180, RunAtLoad=True, ProcessType='Background',
                  EnvironmentVariables={'XDG_RUNTIME_DIR': str(volume / 'station-runtime')},
                  ProgramArguments=list(map(str, args_list)),
                  StandardErrorPath=str(Path.home() / 'Library/Logs/starred-archive.log'))
    agent.parent.mkdir(parents=True, exist_ok=True)
    domain = 'gui/' + str(os.getuid())
    subprocess.run(['launchctl', 'bootout', domain + '/' + label], capture_output=True)
    agent.write_bytes(plistlib.dumps(config))
    subprocess.run(['launchctl', 'bootstrap', domain, str(agent)], check=True)
