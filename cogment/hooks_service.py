from abc import ABC
import traceback

from types import SimpleNamespace
from typing import Dict

from cogment.api.hooks_pb2_grpc import TrialHooksServicer as Servicer
from cogment.api.hooks_pb2 import TrialContext
from cogment.api.common_pb2 import TrialParams
from cogment.utils import list_versions


class TrialHooks(ABC):
    VERSIONS: Dict[str, str]

    def before(self, trial_id, user_id, trial_params):
        pass


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


class HooksService(Servicer):
    def __init__(self, hooks_class, settings):
        self._hooks_class = hooks_class
        self.settings = settings
        self._hooks = hooks_class()

    def PreTrial(self, request, context):
        try:
            print(request)
            result = TrialContext()
            result.CopyFrom(request)

            user_params = _raw_params_to_user_params(request.params,
                                                     self.settings)
            user_params = self._hooks.pre_trial(request.trial_id,
                                                request.user_id,
                                                user_params)

            result.params.CopyFrom(_user_params_to_raw_params(user_params,
                                                              self.settings))

            return result
        except Exception:
            traceback.print_exc()
            raise

    def Version(self, request, context):
        try:
            return list_versions(self._hooks_class)
        except Exception:
            traceback.print_exc()
            raise
