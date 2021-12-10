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

from posixpath import join
import grpc
import grpc.aio  # type: ignore
from prometheus_client import start_http_server as start_prometheus_server
from prometheus_client.core import REGISTRY  # type: ignore

import cogment.api.orchestrator_pb2_grpc as orchestrator_grpc_api
import cogment.api.agent_pb2_grpc as agent_grpc_api
import cogment.api.environment_pb2_grpc as env_grpc_api
import cogment.api.hooks_pb2_grpc as hooks_grpc_api
import cogment.api.datalog_pb2_grpc as datalog_grpc_api
import cogment.api.agent_pb2 as agent_api

from cogment.actor import ActorSession
from cogment.environment import EnvironmentSession
from cogment.prehook import PrehookSession
from cogment.datalog import DatalogSession
from cogment.control import Controller
from cogment.errors import CogmentError
from cogment.agent_service import AgentServicer, get_actor_impl
from cogment.client_service import ClientServicer
from cogment.env_service import EnvironmentServicer
from cogment.hooks_service import PrehookServicer
from cogment.datalog_service import DatalogServicer

import logging
from typing import Callable, Awaitable, Dict, List, Any
from types import ModuleType
import os
import asyncio
from types import SimpleNamespace


DEFAULT_PROMETHEUS_PORT = 8000


class Endpoint:
    """Class representing a remote Cogment endpoint where to connect."""

    def __init__(self, url: str):
        self.url = url
        self.private_key = None
        self.root_certificates = None
        self.certificate_chain = None

    def __str__(self):
        result = f"Endpoint: url = {self.url}, private_key = {self.private_key}"
        result += f", root_certificates = {self.root_certificates}, certificate_chain = {self.certificate_chain}"
        return result

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
    """Class representing a local Cogment endpoint where others can connect."""

    def __init__(self, port: int):
        self.port = port
        self.private_key_certificate_chain_pairs = None
        self.root_certificates = None

    # def set_from_files(private_key_certificate_chain_pairs_file=None, root_certificates_file=None):
    # TODO: This function would need to parse the PEM encoded `private_key_certificate_chain_pairs_file`
    #       to create the list of tuples required (see simpler version in `Endpoint` class above).

    def __str__(self):
        result = f"ServedEndpoint: port = {self.port}"
        result += f", private_key_certificate_chain_pairs = {self.private_key_certificate_chain_pairs}"
        result += f", root_certificates = {self.root_certificates}"
        return result


def _make_client_channel(endpoint: Endpoint):
    if endpoint.url[:7] == "grpc://":
        url = endpoint.url[7:]
    else:
        logging.warning(f"Endpoint URL must be of gRPC type (start with 'grpc://') [{endpoint.url}]")
        url = endpoint.url

    if endpoint.private_key is None:
        channel = grpc.aio.insecure_channel(url)
    else:
        if endpoint.root_certificates:
            root = bytes(endpoint.root_certificates, "utf-8")
        else:
            root = None
        if endpoint.private_key:
            key = bytes(endpoint.private_key, "utf-8")
        else:
            key = None
        if endpoint.certificate_chain:
            certs = bytes(endpoint.certificate_chain, "utf-8")
        else:
            certs = None
        creds = grpc.ssl_channel_credentials(root, key, certs)
        channel = grpc.aio.secure_channel(url, creds)

    return channel


def _make_server(endpoint: ServedEndpoint):
    server = grpc.aio.server()

    address = f"[::]:{endpoint.port}"
    if endpoint.private_key_certificate_chain_pairs is None:
        server.add_insecure_port(address)
    else:
        if endpoint.root_certificates:
            require_client_auth = True
            root = bytes(endpoint.root_certificates, "utf-8")
        else:
            require_client_auth = False
            root = None
        certs = []
        for (key, chain) in endpoint.private_key_certificate_chain_pairs:
            certs.append((bytes(key, "utf-8"), bytes(chain, "utf-8")))
        if not certs:
            certs = None

        creds = grpc.ssl_server_credentials(certs, root, require_client_auth)
        server.add_secure_port(address, creds)

    return server


class Context:
    """Top level class for the Cogment library from which to obtain all services."""

    def __init__(self, user_id: str, cog_settings: ModuleType, asyncio_loop=None, prometheus_registry=REGISTRY):
        self._user_id = user_id
        self._actor_impls: Dict[str, SimpleNamespace] = {}
        self._env_impls: Dict[str, SimpleNamespace] = {}
        self._prehook_impl: Callable[[PrehookSession], Awaitable[None]] = None
        self._datalog_impl: Callable[[DatalogSession], Awaitable[None]] = None
        self._grpc_server = None  # type: Any
        self._prometheus_registry = prometheus_registry
        self._cog_settings = cog_settings

        if asyncio_loop is None:
            # Make sure we are running in a asyncio.Task. Even if technically this init does not need
            # to be in a Task, the whole of the SDK expects to be running in Tasks of the same event loop.
            try:
                self.asyncio_loop = asyncio.get_running_loop()
            except RuntimeError:
                raise CogmentError("The Cogment SDK requires running in a Python `asyncio` Task")
        else:
            self.asyncio_loop = asyncio_loop

    def __str__(self):
        result = f"Cogment Context: user id = {self._user_id}"
        return result

    def register_actor(self,
                       impl: Callable[[ActorSession], Awaitable[None]],
                       impl_name: str,
                       actor_classes: List[str] = []):
        if self._grpc_server is not None:
            # We could accept "client" actor registration after the server is started, but it is not worth it
            raise CogmentError("Cannot register an actor after the server is started")
        if impl_name in self._actor_impls:
            raise CogmentError(f"The actor implementation name must be unique: [{impl_name}]")

        self._actor_impls[impl_name] = SimpleNamespace(impl=impl, actor_classes=actor_classes)

    def register_environment(self,
                             impl: Callable[[EnvironmentSession], Awaitable[None]],
                             impl_name: str = "default"):
        if self._grpc_server is not None:
            raise CogmentError("Cannot register an environment after the server is started")
        if impl_name in self._env_impls:
            raise CogmentError(f"The environment implementation name must be unique: [{impl_name}]")

        self._env_impls[impl_name] = SimpleNamespace(impl=impl)

    def register_pre_trial_hook(self,
                                impl: Callable[[PrehookSession], Awaitable[None]]):
        if self._grpc_server is not None:
            raise CogmentError("Cannot register a pre-trial hook after the server is started")
        if self._prehook_impl is not None:
            raise CogmentError("Only one pre-trial hook service can be registered")

        self._prehook_impl = impl

    def register_datalog(self,
                         impl: Callable[[DatalogSession], Awaitable[None]]):
        if self._grpc_server is not None:
            raise CogmentError("Cannot register a datalog after the server is started")
        if self._datalog_impl is not None:
            raise CogmentError("Only one datalog service can be registered")

        self._datalog_impl = impl

    async def serve_all_registered(self, served_endpoint: ServedEndpoint, prometheus_port=DEFAULT_PROMETHEUS_PORT):
        if (len(self._actor_impls) == 0 and len(self._env_impls) == 0 and
                self._prehook_impl is None and self._datalog_impl is None):
            raise CogmentError("Nothing registered to serve!")
        if self._grpc_server is not None:
            raise CogmentError("Cannot serve the same components twice")

        self._grpc_server = _make_server(served_endpoint)

        if self._actor_impls:
            servicer = AgentServicer(self._actor_impls, self._cog_settings, self._prometheus_registry)
            agent_grpc_api.add_ServiceActorSPServicer_to_server(servicer, self._grpc_server)

        if self._env_impls:
            servicer = EnvironmentServicer(self._env_impls, self._cog_settings, self._prometheus_registry)
            env_grpc_api.add_EnvironmentSPServicer_to_server(servicer, self._grpc_server)

        if self._prehook_impl is not None:
            servicer = PrehookServicer(self._prehook_impl, self._cog_settings, self._prometheus_registry)
            hooks_grpc_api.add_TrialHooksSPServicer_to_server(servicer, self._grpc_server)

        if self._datalog_impl is not None:
            servicer = DatalogServicer(self._datalog_impl, self._cog_settings)
            datalog_grpc_api.add_DatalogSPServicer_to_server(servicer, self._grpc_server)

        if self._prometheus_registry is not None and prometheus_port is not None:
            start_prometheus_server(prometheus_port, "", self._prometheus_registry)

        await self._grpc_server.start()
        logging.debug(f"Context gRPC server at port [{served_endpoint.port}] for user [{self._user_id}] started")
        await self._grpc_server.wait_for_termination()
        logging.debug(f"Context gRPC server at port [{served_endpoint.port}] for user [{self._user_id}] exited")

    def get_controller(self, endpoint: Endpoint):
        channel = _make_client_channel(endpoint)
        stub = orchestrator_grpc_api.TrialLifecycleSPStub(channel)
        return Controller(stub, self._user_id)

    async def join_trial(self, trial_id, endpoint: Endpoint, impl_name=None, actor_name=None, actor_class=None):
        requested_class = None
        requested_name = None
        if impl_name is not None:
            # For backward compatibility
            logging.warning(f"`join_trial` parameter `impl_name` is deprecated")
            if actor_name is None:
                actor_impl = self._actor_impls[impl_name]
                if len(actor_impl.actor_classes) == 0:
                    raise CogmentError(f"Unable to determine possible actor to join trial: "
                                       f"impl_name [{impl_name}] does not have any registered actor class")
                requested_class = actor_impl.actor_classes[0]
            else:
                requested_name = actor_name

        elif actor_name is not None:
            requested_name = actor_name
            if actor_class is not None:
                logging.warning(f"`actor_class` will be ignored because `actor_name` is provided in `join_trial")

        elif actor_class is not None:
            requested_class = actor_class

        else:
            raise CogmentError(f"Actor name or actor class must be specified to join a trial")

        channel = _make_client_channel(endpoint)
        stub = orchestrator_grpc_api.ClientActorSPStub(channel)
        servicer = ClientServicer(self._cog_settings, stub)

        init_data = await servicer.join_trial(trial_id, requested_name, requested_class)
        if not init_data:
            return

        if requested_name is not None and requested_name != init_data.actor_name:
            raise CogmentError(f"Internal failure: Actor name [{requested_name}] requested, received: {init_data}")
        if requested_class is not None and requested_class != init_data.actor_class:
            raise CogmentError(f"Internal failure: Actor class [{requested_class}] requested, received: {init_data}")

        if impl_name is not None and init_data.impl_name and init_data.impl_name != impl_name:
            logging.warning(f"Requested impl_name [{impl_name}] does not match trial impl_name "
                            f"[{init_data.impl_name}]: Requested impl_name will be used.")
            init_data.impl_name = impl_name

        actor_impl = get_actor_impl(trial_id, self._actor_impls, init_data)

        await servicer.run_session(actor_impl.impl, init_data)
