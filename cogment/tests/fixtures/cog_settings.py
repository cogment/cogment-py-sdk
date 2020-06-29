import cogment as _cog
from types import SimpleNamespace
from typing import List
import fixtures.rps_pb2
import fixtures.rps_delta


_player_class = _cog.ActorClass(
    id='player',
    config_type=None,
    action_space=fixtures.rps_pb2.ActorAction,
    observation_space=fixtures.rps_pb2.GameState,
    observation_delta=fixtures.rps_pb2.GameStateDelta,
    observation_delta_apply_fn=fixtures.rps_delta.apply_delta_gs,
    feedback_space=None
)

_judge_class = _cog.ActorClass(
    id='judge',
    config_type=None,
    action_space=fixtures.rps_pb2.JudgeAction,
    observation_space=fixtures.rps_pb2.JudgeView,
    observation_delta=fixtures.rps_pb2.JudgeView,
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
    feedback_space=None
)


actor_classes = _cog.actor_class.ActorClassList(
    _player_class,
    _judge_class,
)


environment = SimpleNamespace(
    config_type=None,
)


class ActionsTable:
    player: List[fixtures.rps_pb2.ActorAction]
    judge: List[fixtures.rps_pb2.JudgeAction]

    def __init__(self, trial):
        self.player = [fixtures.rps_pb2.ActorAction() for _ in range(trial.actor_counts[0])]
        self.judge = [fixtures.rps_pb2.JudgeAction() for _ in range(trial.actor_counts[1])]

    def all_actions(self):
        return self.player + self.judge


class player_ObservationProxy(_cog.env_service.ObservationProxy):
    @property
    def snapshot(self) -> fixtures.rps_pb2.GameState:
        return self._get_snapshot(fixtures.rps_pb2.GameState)

    @snapshot.setter
    def snapshot(self, v):
        self._set_snapshot(v)

    @property
    def delta(self) -> fixtures.rps_pb2.GameStateDelta:
        return self._get_delta(fixtures.rps_pb2.GameStateDelta)

    @delta.setter
    def delta(self, v):
        self._set_delta(v)


class judge_ObservationProxy(_cog.env_service.ObservationProxy):
    @property
    def snapshot(self) -> fixtures.rps_pb2.JudgeView:
        return self._get_snapshot(fixtures.rps_pb2.JudgeView)

    @snapshot.setter
    def snapshot(self, v):
        self._set_snapshot(v)

    @property
    def delta(self) -> fixtures.rps_pb2.JudgeView:
        return self._get_delta(fixtures.rps_pb2.JudgeView)

    @delta.setter
    def delta(self, v):
        self._set_delta(v)


class ObservationsTable:
    player: List[player_ObservationProxy]
    judge: List[judge_ObservationProxy]

    def __init__(self, trial):
        self.player = [player_ObservationProxy() for _ in range(trial.actor_counts[0])]
        self.judge = [judge_ObservationProxy() for _ in range(trial.actor_counts[1])]

    def all_observations(self):
        return self.player + self.judge
