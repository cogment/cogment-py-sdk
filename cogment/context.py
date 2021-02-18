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

import logging
from typing import Callable, Awaitable, Dict, List, Any
from types import ModuleType
import os
import asyncio
from types import SimpleNamespace
import grpc
import grpc.experimental.aio
from prometheus_client import start_http_server, CollectorRegistry

from cogment.actor import ActorSession, ActorClass
from cogment.environment import EnvironmentSession
from cogment.prehook import PrehookSession
from cogment.datalog import DatalogSession
from cogment.control import ControlSession

# Agent
from cogment.agent_service import AgentServicer
from cogment.api.agent_pb2 import _AGENTENDPOINT as agent_endpoint_descriptor
from cogment.api.agent_pb2_grpc import add_AgentEndpointServicer_to_server

# Client
from cogment.client_service import ClientServicer

# Control
from cogment.control_service import ControlServicer

# Environment
from cogment.env_service import EnvironmentServicer
from cogment.api.environment_pb2_grpc import add_EnvironmentEndpointServicer_to_server

# Prehook
from cogment.hooks_service import PrehookServicer
from cogment.api.hooks_pb2_grpc import add_TrialHooksServicer_to_server

# Log Exporter
from cogment.log_exporter_service import LogExporterService
from cogment.api.datalog_pb2_grpc import add_LogExporterServicer_to_server


DEFAULT_MAX_WORKERS = 1
ENABLE_REFLECTION_VAR_NAME = "COGMENT_GRPC_REFLECTION"
DEFAULT_ENABLE_REFLECTION = os.getenv(ENABLE_REFLECTION_VAR_NAME, "false")
DEFAULT_PROMETHEUS_PORT = 8000


def _add_actor_service(grpc_server, impls, service_names, cog_settings, prometheus_registry):
    servicer = AgentServicer(impls, cog_settings, prometheus_registry)
    add_AgentEndpointServicer_to_server(servicer, grpc_server)
    service_names.append(agent_endpoint_descriptor.full_name)


def _add_env_service(grpc_server, impls, cog_settings, prometheus_registry):
    servicer = EnvironmentServicer(impls, cog_settings, prometheus_registry)
    add_EnvironmentEndpointServicer_to_server(servicer, grpc_server)


def _add_prehook_service(grpc_server, impls, cog_settings, prometheus_registry):
    servicer = PrehookServicer(impls, cog_settings, prometheus_registry)
    add_TrialHooksServicer_to_server(servicer, grpc_server)


def _add_datalog_service(grpc_server, impl, cog_settings, prometheus_registry):
    servicer = LogExporterService(impl, cog_settings, prometheus_registry)
    add_LogExporterServicer_to_server(servicer, grpc_server)


class Endpoint:

    def __init__(self, url: str):
        self.url = url
        self.private_key = None
        self.root_certificates = None
        self.certificate_chain = None

    def set_from_files(self, private_key_file=None, root_certificates_file=None, certificate_chain_file=None):
        try:
            if private_key_file:
                with open(private_key_file) as fl:
                    self.private_key = fl.read()
                if not self.private_key:
                    self.private_key = None

            if root_certificates_file:
                with open(root_certificates_file) as fl:
                    self.root_certificates = fl.read()
                if not self.root_certificates:
                    self.root_certificates = None

            if certificate_chain_file:
                with open(certificate_chain_file) as fl:
                    self.certificate_chain = fl.read()
                if not self.certificate_chain:
                    self.certificate_chain = None

        except Exception:
            logging.error(f"Failed loading file from CWD: {os.getcwd()}")
            raise


class ServedEndpoint:

    def __init__(self, port: int):
        self.port = port
        self.private_key_certificate_chain_pairs = None
        self.root_certificates = None

    # def set_from_files(private_key_certificate_chain_pairs_file=None, root_certificates_file=None):
    # TODO: This function would need to parse the PEM encoded `private_key_certificate_chain_pairs_file`
    #       to create the list of tuples required


class Context:
    def __init__(self, user_id: str, cog_settings: ModuleType):
        self._user_id = user_id
        self.__actor_impls: Dict[str, SimpleNamespace] = {}
        self.__env_impls: Dict[str, SimpleNamespace] = {}
        self.__prehook_impls: List[Callable[[PrehookSession], Awaitable[None]]] = []
        self.__datalog_impl: Callable[[DatalogSession], Awaitable[None]] = None
        self._grpc_server = None  # type: Any
        self._prometheus_registry = CollectorRegistry()
        self.__cog_settings = cog_settings

    def register_actor(self,
                       impl: Callable[[ActorSession], Awaitable[None]],
                       impl_name: str,
                       actor_classes: List[str] = []):
        assert impl_name not in self.__actor_impls
        assert self._grpc_server is None

        self.__actor_impls[impl_name] = SimpleNamespace(
            impl=impl, actor_classes=actor_classes
        )

    def register_environment(self,
                             impl: Callable[[EnvironmentSession], Awaitable[None]],
                             impl_name: str = "default"):
        assert impl_name not in self.__env_impls
        assert self._grpc_server is None

        self.__env_impls[impl_name] = SimpleNamespace(impl=impl)

    def register_pre_trial_hook(self,
                                impl: Callable[[PrehookSession], Awaitable[None]]):
        assert self._grpc_server is None

        self.__prehook_impls.append(impl)

    def register_datalog(self,
                         impl: Callable[[DatalogSession], Awaitable[None]]):
        assert self._grpc_server is None
        assert self.__datalog_impl is None

        self.__datalog_impl = impl

    async def serve_all_registered(self,
                                   served_endpoint: ServedEndpoint,
                                   prometheus_port: int = DEFAULT_PROMETHEUS_PORT):

        if self.__actor_impls or self.__env_impls or self.__prehook_impls or self.__datalog_impl is not None:
            self._grpc_server = grpc.experimental.aio.server()

            service_names: List[str] = []
            if self.__actor_impls:
                _add_actor_service(
                    self._grpc_server,
                    self.__actor_impls,
                    service_names,
                    self.__cog_settings,
                    self._prometheus_registry
                )

            if self.__env_impls:
                _add_env_service(
                    self._grpc_server,
                    self.__env_impls,
                    self.__cog_settings,
                    self._prometheus_registry
                )

            if self.__prehook_impls:
                _add_prehook_service(
                    self._grpc_server,
                    self.__prehook_impls,
                    self.__cog_settings,
                    self._prometheus_registry
                )

            if self.__datalog_impl is not None:
                _add_datalog_service(
                    self._grpc_server,
                    self.__datalog_impl,
                    self.__cog_settings,
                    self._prometheus_registry
                )

            start_http_server(prometheus_port, "", self._prometheus_registry)

            address = f"[::]:{served_endpoint.port}"
            if served_endpoint.private_key_certificate_chain_pairs is None:
                self._grpc_server.add_insecure_port(address)
            else:
                if served_endpoint.root_certificates:
                    require_client_auth = True
                    root = bytes(served_endpoint.root_certificates, "utf-8")
                else:
                    require_client_auth = False
                    root = None
                certs = []
                for (key, chain) in served_endpoint.private_key_certificate_chain_pairs:
                    certs.append((bytes(key, "utf-8"), bytes(chain, "utf-8")))
                if not certs:
                    certs = None

                creds = grpc.ssl_server_credentials(certs, root, require_client_auth)
                self._grpc_server.add_secure_port(address, creds)

            await self._grpc_server.start()
            await self._grpc_server.wait_for_termination()
            logging.debug(f"Context gRPC server at port [{served_endpoint.port}] for user [{self._user_id}] exited")

    async def start_trial(self,
                          endpoint: Endpoint,
                          impl: Callable[[ControlSession], Awaitable[None]],
                          trial_config=None):
        servicer = ControlServicer(self.__cog_settings, endpoint)
        await servicer.run(self._user_id, impl, trial_config)

    async def join_trial(self, trial_id, endpoint: Endpoint, impl_name, actor_name=None):
        actor_impl = self.__actor_impls.get(impl_name)
        if actor_impl is None:
            raise Exception(f"Unknown actor impl [{impl_name}].  Was it registered?")

        servicer = ClientServicer(self.__cog_settings, endpoint)
        await servicer.run(trial_id, actor_impl.impl, impl_name, actor_impl.actor_classes, actor_name)
