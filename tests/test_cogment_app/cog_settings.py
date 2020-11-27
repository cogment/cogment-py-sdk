
import cogment as _cog
from types import SimpleNamespace
from typing import List

import data_pb2 as data_pb

protolib = "data_pb2"

_my_actor_class_1_class = _cog.ActorClass(
    id='my_actor_class_1',
    config_type=None,
    action_space=data_pb.Action,
    observation_space=data_pb.Observation,
    observation_delta=data_pb.Observation,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None,
    # TODO remove from the generator
    # message_space=None
)

_my_actor_class_2_class = _cog.ActorClass(
    id='my_actor_class_2',
    config_type=None,
    action_space=data_pb.Action,
    observation_space=data_pb.Observation,
    observation_delta=data_pb.Observation,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None,
    # TODO remove from the generator
    # message_space=None
)


actor_classes = _cog.ActorClassList(
    _my_actor_class_1_class,
    _my_actor_class_2_class,
)

# TODO remove from the generator
# env_class = _cog.EnvClass(
#     id='env',
#     config_type=None,
#     message_space=None
# )

trial = SimpleNamespace(
    config_type=data_pb.TrialConfig,
)

# Environment
environment = SimpleNamespace(
    config_type=data_pb.EnvConfig,
)


class ActionsTable:
    my_actor_class_1: List[data_pb.Action]
    my_actor_class_2: List[data_pb.Action]

    def __init__(self, trial):
        self.my_actor_class_1 = [data_pb.Action() for _ in range(trial.actor_counts[0])]
        self.my_actor_class_2 = [data_pb.Action() for _ in range(trial.actor_counts[1])]

    def all_actions(self):
        return self.my_actor_class_1 + self.my_actor_class_2

