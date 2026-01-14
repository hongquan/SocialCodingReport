import os
from collections.abc import Sequence
from pathlib import Path

import msgspec
from logbook import Logger


CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'socialcodingreport'
CONFIG_FILE = CONFIG_DIR / 'config.toml'

log = Logger(__name__)


class Config(msgspec.Struct):
    repositories: tuple[str, ...] = ()


class ConfigManager:
    def __init__(self):
        self.ensure_config_dir()

    def ensure_config_dir(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def load_repositories(self) -> tuple[str, ...]:
        if not CONFIG_FILE.exists():
            return ()

        try:
            with open(CONFIG_FILE, 'rb') as f:
                content = f.read()
                data = msgspec.toml.decode(content, type=Config)
                return data.repositories
        except (OSError, msgspec.DecodeError) as e:
            log.error('Error loading config: {}', e)
            return ()

    def save_repositories(self, repositories: Sequence[str]):
        config = Config(repositories=tuple(repositories))
        toml_content = msgspec.toml.encode(config)

        try:
            with open(CONFIG_FILE, 'wb') as f:
                f.write(toml_content)
        except OSError as e:
            log.error('Error saving config: {}', e)
