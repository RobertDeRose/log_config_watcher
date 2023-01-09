import logging
import logging.config
from itertools import count
from json import JSONDecodeError, loads
from threading import Thread
from time import sleep


class LogConfigWatcher(Thread):
    __COUNTER = count().__next__

    def __init__(
        self,
        config_file,
        interval=30,
        default_format: str="%(asctime)s | %(threadName)-15.15s | %(levelname)-5.5s | %(message)s",
        default_level: int=logging.DEBUG,
        default_handler: logging.Handler=logging.StreamHandler(),
    ):
        """A Runnable thread that will monitor your logging configuration file for changes and apply them.

        Arguments:
            config_file {Pathlike} -- The location of a JSON logging configuration file to load and monitor

        Keyword Arguments:
            interval {int} -- How often to check the file for changes (default: {30})
            default_format {str} -- The logging format to use before a configuration file is loaded or if it fails to load (default: {"%(asctime)s | %(threadName)-15.15s | %(levelname)-5.5s | %(message)s"})
            default_level {_type_} -- The logging level to use before a configuration file is loaded or if it fails to load (default: {logging.DEBUG})
            default_handler {_type_} -- The logging handler to use before a configuration file is loaded or if it fails to load (default: {logging.StreamHandler()})

        Example:
        ```
        log_watcher = LogConfigWatcher("logging_config.json")
        log_wathcer.start()
        ```
        """
        super().__init__(name=f"LogWatcher-{self.__COUNTER() + 1}", daemon=True)

        self.log = logging.getLogger(__name__)
        self.config_file = config_file
        self.interval = interval

        self._running = True
        self._previous_config = ""

        # Ensure at least a basic logger is ready
        logging.basicConfig(level=default_level, format=default_format, handlers=[default_handler])

        self._update()

    def run(self):
        while self._running:
            self._update()
            sleep(self.interval)

    def stop(self):
        self._running = False

    def _update(self):
        new_config = self._read_config()

        if new_config:
            self._apply_config(new_config)

    def _read_config(self):
        try:
            with open(self.config_file) as config_file:
                new_config = config_file.read()

            if new_config != self._previous_config:
                config_dict = loads(new_config)
                self._previous_config = new_config
                self.log.info("Logging configuration change detected")

                return config_dict
        except FileNotFoundError:
            self.log.error("The logging configuration file %s is missing", self.config_file)
        except JSONDecodeError:
            self.log.exception("The logging config has a syntax error")
        except Exception:
            self.log.exception("Unexpected error while reading logging config file %s", self.config_file)

        return None

    def _apply_config(self, new_config):
        try:
            logging.config.dictConfig(new_config)
            self.log.info("Applied new logging configuration")
        except Exception:
            self.log.exception("Logging configuration file contains errors")
