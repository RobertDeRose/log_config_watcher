#!/bin/sh -e
set -x

autoflake --remove-all-unused-imports --recursive --remove-unused-variables --in-place --ignore-init-module-imports log_config_watcher
black log_config_watcher
isort log_config_watcher
