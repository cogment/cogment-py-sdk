# used to double check that routines using ActionsTable work
import cogment as _cog
from types import SimpleNamespace
from typing import List

import data_pb2 as data_pb


protolib = "data_pb2"

_player_class = _cog.ActorClass(
    id_='player',
    config_type=None,
    action_space=data_pb.Action,
    observation_space=data_pb.Observation,
    observation_delta=data_pb.Observation,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None,
)

_goober_class = _cog.ActorClass(
    id_='goober',
    config_type=None,
    action_space=data_pb.Action,
    observation_space=data_pb.Observation,
    observation_delta=data_pb.Observation,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None,
)


actor_classes = _cog.ActorClassList(
    _player_class,
    _goober_class,
)

env_class = _cog.EnvClass(
    id_='env',
    config_type=None,
)

trial = SimpleNamespace(
    config_type=data_pb.TrialConfig,
)

# Environment
environment = SimpleNamespace(
    config_type=data_pb.EnvConfig,
)

class ActionsTable:
    player: List[data_pb.Action]

    def __init__(self, trial):
        self.player = [data_pb.Action() for _ in range(trial.actor_counts[0])]
        self.goober = [data_pb.Action() for _ in range(trial.actor_counts[1])]

    def all_actions(self):
        return self.player