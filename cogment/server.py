from typing import Callable
import os

# Agent
from cogment.agent_service import AgentServicer
from cogment.api.agent_pb2 import _AGENTENDPOINT as agent_endpoint_descriptor
from cogment.api.agent_pb2_grpc import add_AgentEndpointServicer_to_server

DEFAULT_PORT = 9000
DEFAULT_MAX_WORKERS = 1
DEFAULT_ENABLE_REFLECTION = os.getenv(ENABLE_REFLECTION_VAR_NAME, 'false')


def __add_actor_service(grpc_server, impls, service_names):
    servicer = AgentServicer(impls=impls)
    add_AgentEndpointServicer_to_server(servicer, grpc_server)
    service_names.append(_AGENTENDPOINT)

def __add_env_service(grpc_server, impls):
    # TODO
    pass

def __add_env_service(grpc_server, impls):
    # TODO
    pass

def __add_datalog_service(grpc_server, impls):
    # TODO
    pass

class Server:
    def __init__(self, 
                 max_worker_threads: int = DEFAULT_MAX_WORKERS, 
                 port: int = DEFAULT_PORT):
        self.__actor_impls = {}
        self.__env_impls = {}
        self.__prehook_impls = {}
        self.__datalog_impls = {}
        self.__grpc_server = None
        self.__thread_pool = ThreadPoolExecutor(max_workers=self.max_worker_threads)
        self.__port = port

    def register_actor(self, 
                       impl: Callable[[cogment.Actor, cogment.Trial], Awaitable[None]], 
                       impl_name: str, 
                       actor_class: cogment.ActorClass):
        assert impl_name not in self.__actor_impls
        assert self.__grpc_server is None

        self.__actor_impls[impl_name] = SimpleNamespace(impl=impl, 
                                                        actor_class=actor_class)

    def register_environment(self, impl, impl_name: str):
        assert impl_name not in self.__env_impl
        assert self.__grpc_server is None

        self.__env_impl = impl

    def register_prehook(self, impl, impl_name: str):
        assert impl_name not in self.__prehook_impls
        assert self.__grpc_server is None

        self.__prehook_impls = impl

    def register_datalog(self, impl, impl_name: str):
        assert impl_name not in self.__datalog_impls
        assert self.__grpc_server is None

        self.__datalog_impls = impl

    def run(self):
        assert self.__grpc_server is None

        self._grpc_server = grpc.server(thread_pool=self.__thread_pool)

        if self.__actor_impls:
            __add_actor_service(self._grpc_server, self.__actor_impls)

        if self.__env_impls:
            __add_env_service(self._grpc_server, self.__env_impls)

        if self.__prehook_impls:
            __add_env_service(self._grpc_server, self.__prehook_impls)

        if self.__datalog_impls:
            __add_datalog_service(self._grpc_server, self.__datalog_impls)