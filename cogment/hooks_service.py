import traceback

from types import SimpleNamespace
from typing import Dict

from cogment.api.hooks_pb2_grpc import TrialHooksServicer as Servicer
from cogment.api.hooks_pb2_grpc import TrialHooksServicer
from cogment.api.hooks_pb2 import TrialContext
from cogment.api.common_pb2 import TrialParams
from cogment.utils import list_versions

import atexit
import logging
import asyncio


def _raw_params_to_user_params(params, settings):
    trial_config = None
    if params.HasField("trial_config"):
        trial_config = settings.trial.config_type()
        trial_config.ParseFromString(params.trial_config.content)

    env_config = None
    if(params.environment.HasField("config")):
        env_config = settings.environment.config_type()
        env_config.ParseFromString(params.environment.config.content)

    environment = SimpleNamespace(
        endpoint=params.environment.endpoint,
        config=env_config
    )

    actors = []

    for a in params.actors:
        actor_config = None

        if a.HasField("config"):
            a_c = settings.actor_classes.__getattribute__(a.actor_class)
            actor_config = a_c.config_type()
            actor_config.ParseFromString(a.config.content)

        actor = SimpleNamespace(
            actor_class=a.actor_class,
            endpoint=a.endpoint,
            config=actor_config
        )

        actors.append(actor)

    return SimpleNamespace(
        trial_config=trial_config,
        environment=environment,
        actors=actors,
        max_steps=params.max_steps,
        max_inactivity=params.max_inactivity
    )


def _user_params_to_raw_params(params, settings):
    result = TrialParams()

    result.max_steps = params.max_steps
    result.max_inactivity = params.max_inactivity

    if params.trial_config is not None:
        result.trial_config.content = params.trial_config.SerializeToString()

    result.environment.endpoint = params.environment.endpoint
    if params.environment.config is not None:
        result.environment.config.content = \
            params.environment.config.SerializeToString()

    for a in params.actors:
        actor_pb = result.actors.add()
        actor_pb.actor_class = a.actor_class
        actor_pb.endpoint = a.endpoint
        if a.config is not None:
            actor_pb.config.content = a.config.SerializeToString()

    return result


class PrehookServicer(TrialHooksServicer):

    def __init__(self, prehook_impls, cog_project):

        self.__impls = prehook_impls
        self.__prehook_sessions = {}
        self.__cog_project = cog_project
        atexit.register(self.__cleanup)

        logging.info("Prehook Service started")

    async def PreTrial(self, request, context):

        user_params = _raw_params_to_user_params(request.params,
                                                 self.__cog_project)

        for impl in self.__impls:

            user_params = await impl(user_params)

        reply = TrialContext()
        reply.CopyFrom(request)

        reply.params.CopyFrom(_user_params_to_raw_params(user_params,
                                                         self.__cog_project))

        return reply

    def __cleanup(self):
        for data in self.__prehook_sessions.values():
            pass

        self.__prehook_sessions.clear()

        atexit.unregister(self.__cleanup)
