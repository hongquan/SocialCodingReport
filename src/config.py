import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import msgspec
from logbook import Logger

from .models import Account, RepoInfo


CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'socialcodingreport'
CONFIG_FILE = CONFIG_DIR / 'config.toml'

log = Logger(__name__)


@dataclass
class Config:
    accounts: tuple[Account, ...] = ()
    repositories: tuple[RepoInfo, ...] = ()


class ConfigManager:
    def __init__(self):
        self.ensure_config_dir()

    def ensure_config_dir(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Config:
        if not CONFIG_FILE.exists():
            return Config()

        try:
            return msgspec.toml.decode(CONFIG_FILE.read_bytes(), type=Config)
        except (OSError, msgspec.DecodeError) as e:
            log.error('Error loading config: {}', e)
            return Config()

    def save_config(self, config: Config):
        toml_content = msgspec.toml.encode(config)
        try:
            CONFIG_FILE.write_bytes(toml_content)
        except OSError as e:
            log.error('Error saving config: {}', e)

    def load_repositories(self) -> tuple[RepoInfo, ...]:
        return self.load_config().repositories

    def save_repositories(self, repositories: Sequence[RepoInfo]):
        config = self.load_config()
        new_config = Config(accounts=config.accounts, repositories=tuple(repositories))
        self.save_config(new_config)

    def load_accounts(self) -> tuple[Account, ...]:
        return self.load_config().accounts

    def save_accounts(self, accounts: Sequence[Account]):
        config = self.load_config()
        new_config = Config(accounts=tuple(accounts), repositories=config.repositories)
        self.save_config(new_config)
