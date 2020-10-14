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

from threading import Thread
from typing import Callable, Awaitable, Dict, List
from types import ModuleType
import os
import asyncio
from types import SimpleNamespace
import grpc
import grpc.experimental.aio
from prometheus_client import start_http_server

from cogment.actor import ActorSession, ActorClass
from cogment.environment import EnvironmentSession
from cogment.trial import Trial

# Agent
from cogment.agent_service import AgentServicer
from cogment.api.agent_pb2 import _AGENTENDPOINT as agent_endpoint_descriptor
from cogment.api.agent_pb2_grpc import add_AgentEndpointServicer_to_server

# Environment
from cogment.env_service import EnvironmentServicer
from cogment.api.environment_pb2_grpc import add_EnvironmentEndpointServicer_to_server

# Prehook
from cogment.hooks_service import PrehookServicer
from cogment.api.hooks_pb2_grpc import add_TrialHooksServicer_to_server

# Log Exporter
from cogment.log_exporter_service import LogExporterService
from cogment.api.data_pb2_grpc import add_LogExporterServicer_to_server


DEFAULT_PORT = 9000
DEFAULT_MAX_WORKERS = 1
ENABLE_REFLECTION_VAR_NAME = "COGMENT_GRPC_REFLECTION"
DEFAULT_ENABLE_REFLECTION = os.getenv(ENABLE_REFLECTION_VAR_NAME, "false")
DEFAULT_PROMETHEUS_PORT = 8000


def _add_actor_service(grpc_server, impls, service_names, cog_project):
    servicer = AgentServicer(agent_impls=impls, cog_project=cog_project)
    add_AgentEndpointServicer_to_server(servicer, grpc_server)
    service_names.append(agent_endpoint_descriptor.full_name)


def _add_env_service(grpc_server, impls, cog_project):
    servicer = EnvironmentServicer(env_impls=impls, cog_project=cog_project)
    add_EnvironmentEndpointServicer_to_server(servicer, grpc_server)
    # is service_names used for anything in add_actor_service


def _add_prehook_service(grpc_server, impls, cog_project):
    servicer = PrehookServicer(prehook_impls=impls, cog_project=cog_project)
    add_TrialHooksServicer_to_server(servicer, grpc_server)


def _add_datalog_service(grpc_server, impls, cog_project):
    servicer = LogExporterService(datalog_impls=impls, cog_project=cog_project)
    add_LogExporterServicer_to_server(servicer, grpc_server)
    # pass


class Server:
    def __init__(
        self,
        cog_project: ModuleType,
        port: int = DEFAULT_PORT,
        prometheus_port: int = DEFAULT_PROMETHEUS_PORT,
    ):
        self.__actor_impls: Dict[str, SimpleNamespace] = {}
        self.__env_impls: Dict[str, SimpleNamespace] = {}
        self.__prehook_impls: List[
            Callable[[SimpleNamespace], Awaitable[SimpleNamespace]]
        ] = []
        self.__datalog_impls = None
        self.__grpc_server = None
        self.__port = port
        self.__cog_project = cog_project
        self.__prometheus_port = prometheus_port

    def register_actor(
        self,
        impl: Callable[[ActorSession, Trial], Awaitable[None]],
        impl_name: str,
        actor_class: ActorClass,
    ):
        assert impl_name not in self.__actor_impls
        assert self.__grpc_server is None
        self.__actor_impls[impl_name] = SimpleNamespace(
            impl=impl, actor_class=actor_class
        )

    def register_environment(
        self,
        impl: Callable[[EnvironmentSession, Trial], Awaitable[None]],
        impl_name: str = "default",
    ):
        assert impl_name not in self.__env_impls
        assert self.__grpc_server is None

        self.__env_impls[impl_name] = SimpleNamespace(impl=impl)

    def register_prehook(
        self, impl: Callable[[SimpleNamespace], Awaitable[SimpleNamespace]]
    ):
        assert self.__grpc_server is None

        self.__prehook_impls.append(impl)

    def register_datalog(self, impl):
        assert self.__grpc_server is None
        assert self.__datalog_impls is None

        self.__datalog_impls = impl

    async def run(self):
        start_http_server(DEFAULT_PROMETHEUS_PORT)

        self.__grpc_server = grpc.experimental.aio.server()

        service_names = []

        if self.__actor_impls:
            _add_actor_service(
                self.__grpc_server,
                self.__actor_impls,
                service_names,
                self.__cog_project,
            )

        if self.__env_impls:
            _add_env_service(self.__grpc_server, self.__env_impls, self.__cog_project)

        if self.__prehook_impls:
            _add_prehook_service(
                self.__grpc_server, self.__prehook_impls, self.__cog_project
            )

        if self.__datalog_impls:
            _add_datalog_service(
                self.__grpc_server, self.__datalog_impls, self.__cog_project
            )

        self.__grpc_server.add_insecure_port(f"[::]:{self.__port}")

        await self.__grpc_server.start()
        await self.__grpc_server.wait_for_termination()
