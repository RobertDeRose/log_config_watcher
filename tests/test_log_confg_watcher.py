import atexit
from itertools import count
import json
import logging
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

import pytest

from log_config_watcher import LogConfigWatcher


COUNTER = count(1).__next__
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


def write_text(text, file):
    with open(file, "w") as f:
        f.write(text)
        f.flush()


@pytest.fixture
def mock_config_file():
    config_file = Path("test_config_{}.json".format(COUNTER()))
    write_text(json.dumps(CONFIG), config_file)
    atexit.register(lambda: config_file.unlink())
    return config_file


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


def test_init(mock_config_file, mock_logger):
    with patch("logging.getLogger", return_value=mock_logger):
        watcher = LogConfigWatcher(mock_config_file)
        assert watcher.config_file == mock_config_file
        assert watcher.interval == 30
        assert watcher._running is True
        assert watcher._missing_count == -1
        assert watcher.warn_only_once is False


@patch("logging.getLogger")
@patch("time.sleep")
@patch.object(LogConfigWatcher, "_check_modification_time")
def test_run_and_stop(mock_check_modification_time, mock_sleep, mock_get_logger, mock_config_file):
    mock_logger = MagicMock(spec=logging.Logger)
    mock_get_logger.return_value = mock_logger
    mock_check_modification_time.return_value = False

    watcher = LogConfigWatcher(mock_config_file, interval=1)
    watcher.start()
    time.sleep(0.1)  # Give the thread time to start

    assert watcher.is_alive()
    watcher.stop()
    watcher.join(timeout=2)
    assert not watcher.is_alive()

    mock_sleep.assert_called()


@patch("logging.getLogger")
@patch("logging.config.dictConfig")
@patch.object(LogConfigWatcher, "_check_modification_time")
def test_update_on_file_change(mock_check_modification_time, mock_dict_config, mock_get_logger, mock_config_file):
    mock_get_logger.return_value = MagicMock(spec=logging.Logger)
    mock_check_modification_time.return_value = True

    watcher = LogConfigWatcher(mock_config_file)
    watcher._update()

    mock_dict_config.assert_called_once()
    mock_get_logger.return_value.info.assert_called_with("Applied new logging configuration")


def test_file_not_found(mock_logger):
    non_existent_file = Path("/non/existent/file.json")
    with patch("logging.getLogger", return_value=mock_logger):
        watcher = LogConfigWatcher(non_existent_file)
        assert watcher._missing_count == 0  # Initial detection

        watcher._update()
        assert watcher._missing_count == 1  # After first update
        mock_logger.error.assert_called_once_with("The logging configuration file %s is missing", non_existent_file)
        mock_logger.error.reset_mock()

        for i in range(2, 4):
            watcher._update()
            assert watcher._missing_count == i
            mock_logger.error.assert_not_called()

        watcher._update()
        assert watcher._missing_count == 0  # resets after firing
        mock_logger.error.assert_called_once_with("The logging configuration file %s is missing", non_existent_file)


def test_file_not_found_warn_only_once(mock_logger):
    non_existent_file = Path("/non/existent/file.json")
    with patch("logging.getLogger", return_value=mock_logger):
        watcher = LogConfigWatcher(non_existent_file, warn_only_once=True)
        assert watcher._missing_count == 0  # Initial detection
        mock_logger.error.assert_called_once_with("The logging configuration file %s is missing", non_existent_file)

        mock_logger.error.reset_mock()
        for _ in range(10):  # Multiple updates
            watcher._update()
            assert watcher._missing_count == 0
            mock_logger.error.assert_not_called()  # No more error logs


def test_invalid_json(mock_config_file, mock_logger):
    write_text("invalid json", mock_config_file)
    with patch("logging.getLogger", return_value=mock_logger):
        watcher = LogConfigWatcher(mock_config_file)
        watcher._update()

        mock_logger.exception.assert_called_with("The logging config has a syntax error")


@patch("logging.getLogger")
@patch.object(Path, "open")
def test_unexpected_error(mock_open, mock_get_logger, mock_config_file):
    mock_logger = MagicMock(spec=logging.Logger)
    mock_get_logger.return_value = mock_logger
    mock_open.side_effect = Exception("Unexpected error")

    watcher = LogConfigWatcher(mock_config_file)
    watcher._update()

    mock_logger.exception.assert_called_with("Unexpected error while reading logging config file %s", mock_config_file)


@patch("logging.getLogger")
@patch("logging.config.dictConfig")
def test_config_unchanged(mock_dict_config, mock_get_logger, mock_config_file):
    mock_logger = MagicMock(spec=logging.Logger)
    mock_get_logger.return_value = mock_logger

    watcher = LogConfigWatcher(mock_config_file)
    watcher._update()  # First update
    mock_dict_config.reset_mock()

    watcher._update()  # Second update with no changes
    mock_dict_config.assert_not_called()


def test_check_modification_time(mock_config_file):
    watcher = LogConfigWatcher(mock_config_file)

    # First check should return True (initial read)
    assert watcher._check_modification_time() is True

    # Subsequent check without file modification should return False
    assert watcher._check_modification_time() is False

    # Modify file content
    new_config = CONFIG.copy()
    new_config["root"]["level"] = "WARN"
    mock_config_file.unlink()
    write_text(json.dumps(new_config), mock_config_file)

    # Ensure enough time has passed for all systems to detect the change
    time.sleep(0.2)  # 100 ms should be more than enough for most systems

    # Check should detect the modification
    assert watcher._check_modification_time() is True

    # Subsequent check should return False again
    assert watcher._check_modification_time() is False

    # Test file deletion scenario
    with patch.object(Path, "stat", side_effect=FileNotFoundError):
        assert watcher._check_modification_time() is True


@pytest.mark.parametrize(
    "interval,default_format,default_level,default_handler,warn_only_once,logger_name",
    [
        (60, "%(message)s", logging.INFO, logging.FileHandler("test.log"), False, None),
        (10, "%(levelname)s: %(message)s", logging.WARNING, logging.NullHandler(), True, None),
        (60, "%(message)s", logging.INFO, logging.FileHandler("test.log"), False, "test_watcher"),
    ],
)
def test_custom_init_parameters(
    mock_config_file,
    interval,
    default_format,
    default_level,
    default_handler,
    warn_only_once,
    logger_name,
):
    with patch("logging.basicConfig") as mock_basic_config:
        watcher = LogConfigWatcher(
            mock_config_file,
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
            assert watcher.log.name == "log_config_watcher.log_config_watcher"
        else:
            assert watcher.log.name == logger_name
        mock_basic_config.assert_called_once_with(
            level=default_level, format=default_format, handlers=[default_handler]
        )


def test_file_found_after_missing(mock_config_file, mock_logger):
    with patch("logging.getLogger", return_value=mock_logger):
        watcher = LogConfigWatcher(mock_config_file)
        assert watcher._missing_count == -1  # Initial value

        # Simulate file missing
        with patch.object(Path, "open", side_effect=FileNotFoundError):
            watcher._update()
            assert watcher._missing_count == 0

        # Simulate file found again
        watcher._update()
        assert watcher._missing_count == 0  # Stays at 0 after reset
        mock_logger.info.assert_called_with("Logging configuration change detected")
