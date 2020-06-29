from abc import ABC, abstractmethod
import traceback
import atexit

from cogment.api.environment_pb2_grpc import EnvironmentServicer as Servicer
from cogment.api.environment_pb2 import (EnvStartRequest, EnvStartReply,
                                         EnvUpdateReply, EnvEndReply)
from cogment.api.common_pb2 import Feedback, ObservationData
from cogment.utils import list_versions

from types import SimpleNamespace, ModuleType
from typing import Any, Dict, Tuple

from cogment.trial import Trial


class ObservationProxy:
    _payload = None
    _is_snap = False

    def _get_snapshot(self, snap_type):
        if self._payload and self._is_snap:
            return self._payload

        self._is_snap = True
        self._payload = snap_type()
        return self._payload

    def _set_snapshot(self, v):
        self._is_snap = True
        self._payload = v

    def _get_delta(self, dt_type):
        if self._payload and not self._is_snap:
            return self._payload

        self._is_snap = False
        self._payload = dt_type()
        return self._payload

    def _set_delta(self, v):
        self._is_snap = False
        self._payload = v


def new_actions_table(settings, trial):
    actions_by_actor_class = settings.ActionsTable(trial)
    actions_by_actor_id = actions_by_actor_class.all_actions()

    return actions_by_actor_class, actions_by_actor_id


def pack_observations(obs, obs_set):
    '''
    This converts a project-specific ObservationTable,containing a single
    observation per actor, into the cogment api ObservationSet, which contains
    a list of observations and a mapping specifying which observation each actor
    uses.

    Observations are automatically dedupped, if two actors share the same
    observation, only one will be on the wire.
    '''
    seen_observations = {}

    for o in obs.all_observations():
        obs_id = id(o._payload)

        # The index of the observation for this actor in the observation set.
        obs_key = 0
        try:
            obs_key = seen_observations[obs_id]
        except KeyError:
            obs_key = len(obs_set.observations)

            obs_set.observations.append(ObservationData(
                content=o._payload.SerializeToString(),
                snapshot=o._is_snap
            ))

            seen_observations[obs_id] = obs_key

        obs_set.actors_map.append(obs_key)


class Environment(ABC):
    VERSIONS: Dict[str, str]

    def __init__(self, trial: Trial):
        self.trial = trial
        self.end_trial = False

    @abstractmethod
    def start(self, config):
        pass

    def end(self):
        pass

    @abstractmethod
    def update(self, actions):
        pass


class EnvService(Servicer):
    def __init__(self, env_class, settings):
        assert issubclass(env_class, Environment)

        # We will be managing a pool of environments, keyed by their trial id.
        self._envs: Dict[str, Tuple[Any, Trial]] = {}
        self._env_config_type = settings.environment.config_type
        self._env_class = env_class
        self.settings: ModuleType = settings

        atexit.register(self._cleanup)

        print("Environment service started")

    # The orchestrator is requesting a new environment
    def Start(self, request, context):
        try:
            trial_id = request.trial_id
            if not trial_id:
                raise Exception("You must send a trial_id")
            if trial_id in self._envs:
                raise Exception("trial already exists")

            print(f"spinning up new environment: {trial_id}")

            trial_config = None
            if request.HasField("trial_config"):
                if self.settings.trial.config_type is None:
                    raise Exception("trial config data but no config type")
                trial_config = self.settings.trial.config_type()
                trial_config.ParseFromString(request.trial_config.content)

            # Instantiate the fresh environment
            trial = Trial(trial_id, self.settings, request.actor_counts, trial_config)

            # build an action table.
            actions_by_actor_class, actions_by_actor_id = new_actions_table(
                self.settings, trial)

            trial.actions = actions_by_actor_class
            trial.actions_by_actor_id = actions_by_actor_id

            config = None
            if request.HasField("config"):
                if self._env_config_type is None:
                    raise Exception("This environment isn't expecting a config")

                config = self._env_config_type()
                config.ParseFromString(request.config.content)

            instance = self._env_class(trial)
            initial_observation = instance.start(config)

            self._envs[trial.id] = (instance, trial)

            # Send the initial state of the environment back to the client
            # (orchestrator, normally.)
            reply = EnvStartReply()
            reply.observation_set.tick_id = 0
            reply.observation_set.timestamp.GetCurrentTime()

            pack_observations(initial_observation,
                              reply.observation_set)

            return reply
        except Exception:
            traceback.print_exc()
            raise

    def End(self, request, context):
        try:
            try:
                instance, trial = self._envs[request.trial_id]
                instance.end()
                del self._envs[request.trial_id]
                return EnvEndReply()
            except KeyError as err:
                raise Exception("Trial does not exists."
                                " This might be normal if you just reloaded the code of your Environments.")
        except Exception:
            traceback.print_exc()
            raise

    # The orchestrator is ready for the environment to move forward in time.
    def Update(self, request, context):
        try:
            try:
                instance, trial = self._envs[request.trial_id]
            except KeyError as err:
                raise Exception("trial does not exists")

            len_actions = len(request.action_set.actions)
            len_actors = len(trial.actions_by_actor_id)
            if len_actions != len_actors:
                raise Exception(f"Received {len_actions} actions but have {len_actors} actors")

            for i, action in enumerate(trial.actions_by_actor_id):
                action.ParseFromString(request.action_set.actions[i])

            # Advance time
            observations = instance.update(trial.actions)

            # This must be done AFTER the update, as calls to
            # actor.add_feedback must refer to the past.
            trial.tick_id += 1

            # Send the reply to the requestor.
            reply = EnvUpdateReply()

            reply.end_trial = instance.end_trial
            reply.observation_set.tick_id = trial.tick_id
            reply.observation_set.timestamp.GetCurrentTime()

            pack_observations(observations,
                              reply.observation_set)

            reply.feedbacks.extend(trial._get_all_feedback())

            return reply
        except Exception:
            traceback.print_exc()
            raise

    def Version(self, request, context):
        try:
            return list_versions(self._env_class)
        except Exception:
            traceback.print_exc()
            raise

    def _cleanup(self):
        for instance, _ in self._envs.values():
            instance.end()

        self._envs.clear()

        atexit.unregister(self._cleanup)
