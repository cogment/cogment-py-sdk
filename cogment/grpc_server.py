# Copyright 2020 Artificial Intelligence Redefined <dev+cogment@ai-r.com>
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

import os
import atexit
import signal
import threading
import logging

# from cogment.hooks_service import HooksService, TrialHooks
# from cogment.agent_service import AgentService, Agent
# from cogment.env_service import EnvService, Environment
from cogment.utils import list_versions

import cogment.api.hooks_pb2_grpc as grpc_hooks_api
import cogment.api.environment_pb2_grpc as grpc_env_api
import cogment.api.agent_pb2_grpc as grpc_agent_api

from cogment.api.environment_pb2 import _ENVIRONMENTENDPOINT as env_descriptor
from cogment.api.agent_pb2 import _AGENTENDPOINT as agent_descriptor
from cogment.api.hooks_pb2 import _TRIALHOOKS as hooks_descriptor

# from cogment.errors import ConfigError
from cogment.reloader import run_with_reloader

from grpc_reflection.v1alpha import reflection
from concurrent.futures import ThreadPoolExecutor
import grpc

from distutils.util import strtobool

ENABLE_REFLECTION_VAR_NAME = 'COGMENT_GRPC_REFLECTION'
ENABLE_GRPC_SERVER_AUTORELOAD_VAR_NAME = 'COGMENT_GRPC_SERVER_RELOAD'
DEFAULT_PORT = 9000
MAX_WORKERS = 10


# A Grpc endpoint serving a cogment service
class GrpcServer:
    def __init__(self, service_type, settings, port=DEFAULT_PORT):
        self.__exit_handler = None
        self._port = port
        self._grpc_server = grpc.server(ThreadPoolExecutor(
            max_workers=MAX_WORKERS))

        self._service_types = []

        if isinstance(service_type, list):
            for s in service_type:
                self._add_service(s, settings)
        else:
            self._add_service(service_type, settings)

        # Enable grpc reflection if requested
        if strtobool(os.getenv(ENABLE_REFLECTION_VAR_NAME, 'false')):
            service_names = [s.full_name for s in self._service_types] + [reflection.SERVICE_NAME]
            reflection.enable_server_reflection(service_names, self._grpc_server)

        self.__auto_reload = strtobool(os.getenv(ENABLE_GRPC_SERVER_AUTORELOAD_VAR_NAME, 'false'))

        # Give the server a chance to properly shutdown when running in auto_reload mode. Note, we cannot do this
        # by capturing signals as the server is not running in the main thread, when auto_reload is on.
        if self.__auto_reload:
            self.__exit_handler = self.stop
            atexit.register(self.__exit_handler)

        # This check is required because when auto_reload is requested is on the grpc_server won't be launched from
        # the main thread so attempting to capture any of the signals below will just raise an exception.
        if threading.current_thread() is threading.main_thread():
            for sig in ('TERM', 'HUP', 'INT'):
                signal.signal(getattr(signal, 'SIG' + sig), self.stop)

    def _add_service(self, service_type, settings):
        """Adds a service to the grpc server.
           This only works before the server is actually started."""
        logging.info(f"Versions for {service_type.__name__}:")
        for v in list_versions(service_type).versions:
            logging.info(f'  {v.name}: {v.version}')

        # Register service
        if issubclass(service_type, Agent):
            self._service_types.append(agent_descriptor)
            grpc_agent_api.add_AgentEndpointServicer_to_server(
                AgentService(service_type, settings), self._grpc_server)
        elif issubclass(service_type, Environment):
            self._service_types.append(env_descriptor)
            grpc_env_api.add_EnvironmentEndpointServicer_to_server(
                EnvService(service_type, settings), self._grpc_server)
        elif issubclass(service_type, TrialHooks):
            self._service_types.append(hooks_descriptor)
            grpc_hooks_api.add_TrialHooksServicer_to_server(
                HooksService(service_type, settings), self._grpc_server)
        else:
            raise ConfigError('Invalid service type')

    def __run(self):
        self._grpc_server.add_insecure_port(f'[::]:{self._port}')
        self._grpc_server.start()

        for s in self._service_types:
            logging.info(f"{s.full_name} service listening on port {self._port}")

        self._grpc_server.wait_for_termination()

    def serve(self):
        if self.__auto_reload:
            run_with_reloader(self.__run)
        else:
            self.__run()

    def stop(self, *args):
        if self.__exit_handler:
            atexit.unregister(self.__exit_handler)
            self.__exit_handler = None

        self._grpc_server.stop(0).wait()
