from itertools import count
from json import JSONDecodeError, loads
import logging
import logging.config
from pathlib import Path
from threading import Thread
from time import sleep


class LogConfigWatcher(Thread):
    __COUNTER = count(1).__next__

    def __init__(
        self,
        config_file,
        interval=30,
        default_format="%(asctime)s | %(threadName)-15.15s | %(levelname)-5.5s | %(message)s",
        default_level=logging.DEBUG,
        default_handler=logging.StreamHandler(),
        warn_only_once=False,
        logger_name=None,
    ):
        """A Runnable thread that will monitor your logging configuration file for changes and apply them.

        Arguments:
            config_file {Pathlike} -- The location of a JSON logging configuration file to load and monitor

        Keyword Arguments:
            interval {int} -- How often to check the file for changes (default: {30})
            default_format {str} -- The logging format to use before a configuration file is loaded or if it fails to load (default: {"%(asctime)s | %(threadName)-15.15s | %(levelname)-5.5s | %(message)s"})
            default_level {_type_} -- The logging level to use before a configuration file is loaded or if it fails to load (default: {logging.DEBUG})
            default_handler {_type_} -- The logging handler to use before a configuration file is loaded or if it fails to load (default: {logging.StreamHandler()})
            warn_only_once {bool} -- If true, only warn once if the configuration file is missing (default: {False})

        Example:
        ```
        log_watcher = LogConfigWatcher("logging_config.json")
        log_wathcer.start()
        ```
        """
        super().__init__(name="LogWatcher-{}".format(self.__COUNTER()), daemon=True)

        self.log = logging.getLogger(logger_name or __name__)
        self.config_file = Path(config_file)
        self.interval = interval
        self.warn_only_once = warn_only_once

        self._running = True
        self._previous_config = ""
        self._missing_count = -1  # we start at -1 because we want the first miss to log but then only ever 4th time
        self._last_file_size = 0
        self._last_mtime = 0
        self._last_ctime = 0
        self._last_inode = 0
        self._warned = False

        # Ensure at least a basic logger is ready
        logging.basicConfig(level=default_level, format=default_format, handlers=[default_handler])

        self._update()

    def run(self):
        while self._running:
            if self._check_modification_time():
                self._update()
            sleep(self.interval)

    def stop(self):
        self._running = False

    def _update(self):
        new_config = self._read_config()

        if new_config:
            self._apply_config(new_config)

    def _check_modification_time(self):
        try:
            file_stat = self.config_file.stat()
            new_mtime = file_stat.st_mtime_ns
            new_ctime = file_stat.st_ctime_ns
            new_inode = file_stat.st_ino
            new_size = file_stat.st_size

            # Check if modification time, inode, link count, or size has changed
            if (
                new_mtime != self._last_mtime
                or new_ctime != self._last_ctime
                or new_inode != self._last_inode
                or new_size != self._last_file_size
            ):
                self._last_mtime = new_mtime
                self._last_ctime = new_ctime
                self._last_inode = new_inode
                self._last_file_size = new_size
                return True
        except FileNotFoundError:
            return True
        return False

    def _read_config(self):
        try:
            with self.config_file.open("r") as config_file:
                new_config = config_file.read()

            if new_config != self._previous_config:
                config_dict = loads(new_config)
                self._previous_config = new_config
                self.log.info("Logging configuration change detected")

                return config_dict
        except FileNotFoundError:
            if self.warn_only_once and self._warned:
                return None

            self._missing_count += 1
            if self._missing_count % 4 == 0:
                self.log.error("The logging configuration file %s is missing", self.config_file)
                self._warned = True
                self._missing_count = 0
        except JSONDecodeError:
            self.log.exception("The logging config has a syntax error")
        except Exception:
            self.log.exception(
                "Unexpected error while reading logging config file %s",
                self.config_file,
            )

        return None

    def _apply_config(self, new_config):
        try:
            logging.config.dictConfig(new_config)
            self.log.info("Applied new logging configuration")
        except Exception:
            self.log.exception("Logging configuration file contains errors")
