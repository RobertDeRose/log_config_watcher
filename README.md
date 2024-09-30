# Log Config Watcher

This library makes it easy to load a JSON formatted Python Logging configuration file
and monitor the file for changes. If the configuration has changed, and is valid, it will
automatically be applied and the changes will be reflect in your logging without restarting.

## Getting Started

```python
from log_config_watcher import LogConfigWatcher

log_watcher = LogConfigWatcher("config.json")
log_Watcher.start()
```

## Options

The `LogConfigWatcher` class using the Python logging system to setup a `basicConfig` before
attempting to load the config file. This way if there are any errors during the loading of the file
they will be reported somewhere. You can customize the defaults using the following settings passed
to the constructor.

* default_level: int - A Python logging logging level, such as, DEBUG, INFO, WARNING, or ERROR
* default_format: str - A Python logging format string
* default_handler: logging.Handler - A Python logging Handler type, such as, StreamHandler, FileHandler, etc, etc

## Development

This project uses [Poetry](https://python-poetry.org/) as its project manager.
The goal of this library is to have no external runtime dependencies.
However, for development, the following are used:

* [pytest](https://pytest.org/) - For running tests
* [pre-commit](https://pre-commit.com) - Pre-commit hooks to check formatting and lots of other things
  * PR will automatically run these check and fail if they don't pass
