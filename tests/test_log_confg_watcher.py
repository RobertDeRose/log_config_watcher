import configparser

from log_config_watcher import __version__


def test_version():
    parser = configparser.ConfigParser()
    parser.read("pyproject.toml")
    version = parser["tool.poetry"]["version"].strip('"')
    assert __version__ == version
