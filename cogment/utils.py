# Copyright 2023 AI Redefined Inc. <dev+cogment@ai-r.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import grpc
import psutil

import cogment.api.common_pb2 as common_api

from cogment.version import __version__

import logging
import types
import typing
import os


def _logger_trace(self, msg, *args, **kwargs):
    """Simplified trace log output method"""
    self.log(self.TRACE, msg, *args, **kwargs)


def _logger_deprecated(self, msg):
    """Log deprecation as warning but only once"""
    if msg not in self.DEPRECATED_LOGGED:
        self.warning(msg)
        self.DEPRECATED_LOGGED.add(msg)


def make_logger(name, env_name=None, default_level="INFO"):
    # `logger` type is set to `Any` to stop pylint from complaining
    # about: '"Logger" has no attribute "deprecated"'. Similarly for "trace".
    logger: typing.Any = logging.getLogger(name)
    setattr(logger, "TRACE", 5)  # We don't want a new global level name (i.e. with 'logging.addLevelName')
    setattr(logger, "trace", types.MethodType(_logger_trace, logger))
    setattr(logger, "DEPRECATED_LOGGED", set())
    setattr(logger, "deprecated", types.MethodType(_logger_deprecated, logger))

    if env_name is not None:
        log_level = os.environ.get(env_name, default_level).upper()
    else:
        log_level = default_level.upper()

    if log_level == "OFF":
        logger.setLevel(logging.CRITICAL)
    elif log_level == "TRACE":
        logger.setLevel(logger.TRACE)
    else:
        logger.setLevel(log_level)

    return logger


logger = make_logger("cogment.sdk", "COGMENT_LOG_LEVEL")


# Timeout (in seconds) for the init data to come from the Orchestrator before we consider a failure.
INIT_TIMEOUT = 30


def list_versions():
    reply = common_api.VersionInfo()
    reply.versions.add(name='cogment_sdk', version=__version__)
    reply.versions.add(name='grpc', version=grpc.__version__)

    return reply


# Normally [0-100], representing machine load.
# But "loadavg" may give > 1 per cpu on Linux.
# Actual range is [0-254] (to work with Cogment Directory load balancing).
def machine_load() -> int:
    cpu_count = psutil.cpu_count()
    if cpu_count is None or cpu_count == 0:
        cpu_count = len(psutil.cpu_percent(percpu=True))
    if cpu_count is None or cpu_count == 0:
        return None

    float_load = 100.0 * (psutil.getloadavg()[0] / cpu_count)
    load = max(0, min(int(float_load), 254))

    return load
