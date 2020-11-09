
import cogment as _cog
from types import SimpleNamespace
from typing import List

import data_pb2 as data_pb


protolib = "data_pb2"

_my_actor_class_class = _cog.ActorClass(
    id='my_actor_class',
    config_type=None,
    action_space=data_pb.My_actor_classAction,
    observation_space=data_pb.Observation,
    observation_delta=data_pb.Observation,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None,
    message_space=None
)

_my_agent_class_1_class = _cog.ActorClass(
    id='my_agent_class_1',
    config_type=None,
    action_space=data_pb.My_agent_class_1Action,
    observation_space=data_pb.Observation,
    observation_delta=data_pb.Observation,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None,
    message_space=None
)

_my_agent_class_2_class = _cog.ActorClass(
    id='my_agent_class_2',
    config_type=None,
    action_space=data_pb.My_agent_class_2Action,
    observation_space=data_pb.Observation,
    observation_delta=data_pb.Observation,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None,
    message_space=None
)


actor_classes = _cog.actor_class.ActorClassList(
    _my_actor_class_class,
    _my_agent_class_1_class,
    _my_agent_class_2_class,
)

env_class = _cog.EnvClass(
    id='env',
    config_type=None,
    message_space=None
)

trial = SimpleNamespace(
    config_type=data_pb.TrialConfig,
)

# Environment
environment = SimpleNamespace(
    config_type=data_pb.EnvConfig,
)


class ActionsTable:
    my_actor_class: List[data_pb.My_actor_classAction]
    my_agent_class_1: List[data_pb.My_agent_class_1Action]
    my_agent_class_2: List[data_pb.My_agent_class_2Action]

    def __init__(self, trial):
        self.my_actor_class = [data_pb.My_actor_classAction() for _ in range(trial.actor_counts[0])]
        self.my_agent_class_1 = [data_pb.My_agent_class_1Action() for _ in range(trial.actor_counts[1])]
        self.my_agent_class_2 = [data_pb.My_agent_class_2Action() for _ in range(trial.actor_counts[2])]

    def all_actions(self):
        return self.my_actor_class + self.my_agent_class_1 + self.my_agent_class_2

