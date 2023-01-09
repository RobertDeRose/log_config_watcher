import configparser
from .log_config_watcher import LogConfigWatcher

parser = configparser.ConfigParser()
parser.read("pyproject.toml")
__version__ = parser["tool.poetry"]["version"].strip('"')

__all__ = ["__version__", "LogConfigWatcher"]
