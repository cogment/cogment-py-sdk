# Copyright 2021 AI Redefined Inc. <dev+cogment@ai-r.com>
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

import cogment.api.common_pb2 as common_api

from cogment.version import __version__


# logging level for "trace" (i.e. repeated output in critical path) since Python logging does not have a TRACE level
# Use: logging.log(TRACE, f"This is a trace message for {my_pgm}")
TRACE = 5

# Timeout (in seconds) for the init data to come from the Orchestrator before we consider a failure.
INIT_TIMEOUT = 30


def list_versions():
    reply = common_api.VersionInfo()
    reply.versions.add(name='cogment_sdk', version=__version__)
    reply.versions.add(name='grpc', version=grpc.__version__)

    return reply
