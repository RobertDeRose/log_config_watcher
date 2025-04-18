import json
import time
import logging
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from log_config_watcher import LogConfigWatcher


CONFIG = {
    "version": 1,
    "formatters": {"default": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": "INFO",
        }
    },
    "root": {"level": "WARN", "handlers": ["console"]},
}


@pytest.fixture
def mock_config_file(tmp_path):
    config_file = tmp_path / "logging_config.json"
    config_file.write_text(json.dumps(CONFIG))
    return config_file


@pytest.fixture
def mock_logger():
    mock = MagicMock(spec=logging.Logger)
    with patch("logging.getLogger", return_value=mock):
        yield mock


@pytest.fixture
def mock_basic_config():
    with patch("logging.basicConfig") as mock:
        yield mock


@pytest.fixture
def mock_dict_config():
    with patch("logging.config.dictConfig") as mock:
        yield mock


def test_successful_initial_load(mock_config_file, mock_logger):
    watcher = LogConfigWatcher(mock_config_file)
    assert watcher.config_file == mock_config_file
    assert watcher.interval == 30
    assert watcher._running is True
    assert watcher._missing_count == -1
    assert watcher.warn_only_once is False
    mock_logger.info.assert_not_called()
    mock_logger.warning.assert_not_called()
    mock_logger.error.assert_not_called()
    mock_logger.debug.assert_not_called()
    return watcher


@patch("time.sleep")
@patch.object(LogConfigWatcher, "_check_modification_time")
def test_run_and_stop(mock_check_modification_time, mock_sleep, mock_config_file):
    mock_check_modification_time.return_value = False

    watcher = LogConfigWatcher(mock_config_file, interval=1)
    watcher.start()
    time.sleep(0.1)  # Give the thread time to start

    assert watcher.is_alive()
    watcher.stop()
    watcher.join(timeout=2)
    assert not watcher.is_alive()

    mock_sleep.assert_called()


def test_update_on_file_change(mock_logger, mock_dict_config, mock_config_file):
    watcher = LogConfigWatcher(mock_config_file)
    mock_dict_config.assert_called_once()
    mock_logger.info.assert_not_called()
    mock_logger.warning.assert_not_called()
    mock_logger.error.assert_not_called()
    mock_logger.debug.assert_not_called()

    new_config = CONFIG.copy()
    new_config.update({"root": {"level": "DEBUG"}})  # Simulate file change
    mock_config_file.write_text(json.dumps(new_config))  # Simulate file change
    watcher._update()

    mock_dict_config.assert_called_with(new_config)
    mock_logger.info.assert_has_calls(
        [call("Logging configuration change detected"), call("Applied new logging configuration")]
    )


def test_file_not_found(mock_config_file, mock_logger):
    mock_config_file.unlink()
    watcher = LogConfigWatcher(mock_config_file)
    assert watcher._missing_count == 0  # Initial detection

    watcher._update()
    assert watcher._missing_count == 1  # After first update
    mock_logger.error.assert_called_once_with("The logging configuration file %s is missing", mock_config_file)
    mock_logger.error.reset_mock()

    for i in range(2, 4):
        watcher._update()
        assert watcher._missing_count == i
        mock_logger.error.assert_not_called()

    watcher._update()
    assert watcher._missing_count == 0  # resets after firing
    mock_logger.error.assert_called_once_with("The logging configuration file %s is missing", mock_config_file)
    return watcher


def test_file_found_after_missing(mock_config_file, mock_logger):
    watcher = test_file_not_found(mock_config_file, mock_logger)

    # Simulate file found again
    mock_config_file.write_text(json.dumps(CONFIG))
    watcher._update()
    assert watcher._missing_count == -1  # Stays at 0 after reset


def test_file_not_found_warn_only_once(mock_logger):
    non_existent_file = Path("/non/existent/file.json")

    watcher = LogConfigWatcher(non_existent_file, warn_only_once=True)
    assert watcher._missing_count == 0  # Initial detection
    mock_logger.error.assert_called_once_with("The logging configuration file %s is missing", non_existent_file)

    mock_logger.error.reset_mock()
    for _ in range(10):  # Multiple updates
        watcher._update()
        assert watcher._missing_count == 0
        mock_logger.error.assert_not_called()  # No more error logs


def test_invalid_json(mock_config_file, mock_logger):
    mock_config_file.write_text("{invalid_json}")  # Simulate invalid JSON

    LogConfigWatcher(mock_config_file)
    mock_logger.exception.assert_called_with("The logging configuration file %s has syntax errors", mock_config_file)


def test_invalid_json_after_initial_load(mock_config_file, mock_logger):
    watcher = test_successful_initial_load(mock_config_file, mock_logger)

    mock_config_file.write_text("{invalid_json}")  # Simulate invalid JSON
    watcher._update()
    mock_logger.exception.assert_called_with("The logging configuration file %s has syntax errors", mock_config_file)


@patch.object(Path, "open")
def test_unexpected_error(mock_open, mock_logger, mock_config_file):
    mock_open.side_effect = Exception("Unexpected error")

    watcher = LogConfigWatcher(mock_config_file)
    watcher._update()

    mock_logger.exception.assert_called_with("Unexpected error while reading logging config file %s", mock_config_file)


@patch.object(Path, "open")
def test_unexpected_error(mock_open, mock_logger, mock_config_file):
    mock_open.side_effect = PermissionError("You don't own this file")

    watcher = LogConfigWatcher(mock_config_file)
    watcher._update()

    mock_logger.exception.assert_called_with("The logging configuration file %s is not accessible", mock_config_file)


def test_config_unchanged(mock_dict_config, mock_config_file):
    watcher = LogConfigWatcher(mock_config_file)
    watcher._update()  # First update
    mock_dict_config.reset_mock()

    watcher._update()  # Second update with no changes
    mock_dict_config.assert_not_called()


def test_check_modification_time(mock_config_file):
    watcher = LogConfigWatcher(mock_config_file)

    # First check should return True (initial read)
    assert watcher._previous_config is not None
    assert watcher._last_file_size > 0
    assert watcher._last_mtime > 0
    assert watcher._last_ctime > 0
    assert watcher._last_inode > 0

    # Subsequent check without file modification should return False
    assert watcher._check_modification_time() is False

    # Modify file content
    new_config = CONFIG.copy()
    new_config.update({"root": {"level": "WARN"}})
    mock_config_file.write_text(json.dumps(new_config))

    # Ensure enough time has passed for all systems to detect the change
    time.sleep(0.2)  # 100 ms should be more than enough for most systems

    # Check should detect the modification
    assert watcher._check_modification_time() is True

    # Subsequent check should return False again
    assert watcher._check_modification_time() is False

    # Test file deletion scenario
    mock_config_file.unlink()
    assert watcher._check_modification_time() is True


@pytest.mark.parametrize(
    "interval,default_format,default_level,default_handler,warn_only_once,logger_name",
    [
        (60, "%(message)s", logging.INFO, logging.FileHandler("test.log"), False, None),
        (10, "%(levelname)s: %(message)s", logging.WARNING, logging.NullHandler(), True, None),
        (60, "%(message)s", logging.INFO, logging.FileHandler("test.log"), False, "test_watcher"),
    ],
)
def test_custom_init_parameters_for_missing_config(
    interval, default_format, default_level, default_handler, warn_only_once, logger_name, mock_basic_config
):
    watcher = LogConfigWatcher(
        "missing_config.json",
        interval=interval,
        default_format=default_format,
        default_level=default_level,
        default_handler=default_handler,
        warn_only_once=warn_only_once,
        logger_name=logger_name,
    )

    assert watcher.interval == interval
    assert watcher.warn_only_once == warn_only_once
    if logger_name is None:
        assert watcher.log.name == "LogWatcher"
    else:
        assert watcher.log.name == logger_name

    mock_basic_config.assert_any_call(level=logging.ERROR, format=default_format, handlers=[default_handler])
    mock_basic_config.assert_any_call(level=default_level, format=default_format, handlers=[default_handler])


def test_large_configuration_file(mock_config_file, mock_logger, mock_dict_config):
    watcher = test_successful_initial_load(mock_config_file, mock_logger)

    # Generate a large configuration file
    large_config = {
        "version": 1,
        "formatters": {"default": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"}},
        "handlers": {
            "handler_{}".format(i): {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "INFO",
            }
            for i in range(10000)  # Simulate 10000 handlers
        },
        "root": {"level": "WARN", "handlers": ["handler_{}".format(i) for i in range(10000)]},
    }
    mock_config_file.write_text(json.dumps(large_config, indent=2))
    watcher._update()

    # Ensure the large configuration is applied
    mock_dict_config.assert_called_with(large_config)
    mock_logger.info.assert_has_calls(
        [call("Logging configuration change detected"), call("Applied new logging configuration")]
    )
