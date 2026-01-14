import os
import sys


# Add src to path
sys.path.append(os.getcwd())

from config import ConfigManager


try:
    print('Initializing ConfigManager...')
    cm = ConfigManager()
    print(f'Config dir ensured: {cm.ensure_config_dir()}')

    repos = ['test/repo']
    print(f'Saving repos: {repos}')
    cm.save_repositories(repos)

    print('Checking if file exists...')
    from config import CONFIG_FILE

    if CONFIG_FILE.exists():
        print(f'File exists at {CONFIG_FILE}')
    else:
        print(f'File NOT FOUND at {CONFIG_FILE}')

    loaded = cm.load_repositories()
    print(f'Loaded repos: {loaded}')

    if tuple(repos) == loaded:
        print('SUCCESS')
    else:
        print('FAILURE')

except Exception as e:
    print(f'EXCEPTION: {e}')
