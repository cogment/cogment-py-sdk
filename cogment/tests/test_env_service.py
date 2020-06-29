# from cogment import DataTypes
from cogment.env_service import (Environment, EnvService, EnvStartReply,
                                 EnvUpdateReply, EnvEndReply, Trial)
from datetime import datetime
from time import time
from types import SimpleNamespace
from cogment import ActorClass

# import cogment.api.common_pb2 as common_pb
import cogment.api.environment_pb2 as env_pb
import cogment.api.common_pb2 as common_pb
import pytest
import fixtures.rps_pb2 as rps_pb2

import fixtures.cog_settings as settings

TRIAL_ID = "12345"


# types_no_config = DataTypes()
# types_with_config = DataTypes(env_config=common_pb.VersionInfo)


class EmptyEnvClass(Environment):

    def start(self, config):
        obs = rps_pb2.GameState(p1_score=4)
        result = settings.ObservationsTable(self.trial)
        for o in result.all_observations():
            o.snapshot = obs
        return result

    def update(self, actions):
        self.trial.actors.player[0].add_feedback(
                tick_id=3, value=0.5, confidence=1)

        dt = rps_pb2.GameStateDelta(result=rps_pb2.P1_WON)
        result = settings.ObservationsTable(self.trial)
        for o in result.all_observations():
            o.delta = dt
        return result


@pytest.fixture
def empty_env_class():
    return EmptyEnvClass


# @pytest.fixture
# def cogment_settings(with_config: bool):
#     tmp_class = ActorClass(
#         name='player',
#         action_space=rps_pb2.ActorAction,
#         observation_space=rps_pb2.GameState,
#         reward_space=None)

#     config = ??? if with_config else None
#     settings = SimpleNamespace(
#         actor_classes=SimpleNamespace(player=tmp_class),
#         SimpleNamespace(
#             config=None,
#             default_observation=rps_pb2.GameState,
#             actors=[(tmp_class, 2), ]
#         )
#     )

#     return settings


def test_should_raise_if_env_not_environment():
    class EnvWithoutInheritance():
        pass

    with pytest.raises(AssertionError):
        EnvService(EnvWithoutInheritance, settings)


def test_should_raise_without_trial_id(empty_env_class):
    sut = EnvService(empty_env_class, settings)
    req = env_pb.EnvStartRequest()

    with pytest.raises(Exception, match=r".* send a trial_id"):
        sut.Start(req, {})


def test_should_raise_if_trial_id_already_exists(empty_env_class):
    sut = EnvService(empty_env_class, settings)
    req = env_pb.EnvStartRequest(trial_id="12345", actor_counts=[3, 1])
    sut.Start(req, {})

    with pytest.raises(Exception, match=r"trial already exists"):
        sut.Start(req, {})


def test_should_start_env_without_config(empty_env_class):
    sut = EnvService(empty_env_class, settings)
    req = env_pb.EnvStartRequest(trial_id=TRIAL_ID, actor_counts=[3, 1])
    reply = sut.Start(req, {})

    assert type(reply) is EnvStartReply
    assert reply.observation_set.tick_id == 0
    assert time() - reply.observation_set.timestamp.ToSeconds() < 1
    assert reply.observation_set.observations[0].snapshot is True

    assert len(sut._envs) == 1

    gs = rps_pb2.GameState()
    gs.ParseFromString(reply.observation_set.observations[0].content)
    assert gs.p1_score == 4

    assert reply.observation_set.actors_map == [0, 0, 0, 0]


def test_should_catch_exception_on_agent_init(empty_env_class):
    class MyEnv(empty_env_class):
        def __init__(self, trial):
            raise Exception("raise in init")

    sut = EnvService(MyEnv, settings)
    req = env_pb.EnvStartRequest(trial_id=TRIAL_ID, actor_counts=[3, 1])

    with pytest.raises(Exception, match=r"raise in init"):
        sut.Start(req, {})


def test_should_start_and_handle_env_config(empty_env_class):
    sut = EnvService(empty_env_class, settings)

    env_config = common_pb.EnvironmentConfig(
        content="bytes".encode()
    )

    req = env_pb.EnvStartRequest(trial_id=TRIAL_ID, config=env_config, actor_counts=[3, 1])
    with pytest.raises(Exception, match=r"This environment isn't expecting a config"):
        sut.Start(req, {})


def test_should_raise_if_trial_id_not_exist(empty_env_class):
    sut = EnvService(empty_env_class, settings)

    req = env_pb.EnvUpdateRequest(trial_id=TRIAL_ID)

    with pytest.raises(Exception, match=r"trial does not exists"):
        sut.Update(req, {})


def test_should_raise_if_1_action_2_actors(empty_env_class):
    sut = EnvService(empty_env_class, settings)
    req = env_pb.EnvStartRequest(trial_id=TRIAL_ID, actor_counts=[3, 1])
    reply = sut.Start(req, {})

    action_set = env_pb.ActionSet()
    action = rps_pb2.ActorAction(decision=rps_pb2.ROCK)

    action_set.actions.append(action.SerializeToString())

    req = env_pb.EnvUpdateRequest(trial_id=TRIAL_ID, action_set=action_set)

    with pytest.raises(Exception, match=r"Received 1 actions but have .* actors"):
        sut.Update(req, {})


def test_should_update_environment(empty_env_class):
    sut = EnvService(empty_env_class, settings)
    req = env_pb.EnvStartRequest(trial_id=TRIAL_ID, actor_counts=[3, 1])
    reply = sut.Start(req, {})

    action_set = env_pb.ActionSet()
    action = rps_pb2.ActorAction(decision=rps_pb2.ROCK)
    judge_action = rps_pb2.JudgeAction(decision=rps_pb2.P2_WON)

    action_set.actions.append(action.SerializeToString())
    action_set.actions.append(action.SerializeToString())
    action_set.actions.append(action.SerializeToString())
    action_set.actions.append(judge_action.SerializeToString())

    req = env_pb.EnvUpdateRequest(trial_id=TRIAL_ID, action_set=action_set)
    reply = sut.Update(req, {})

    assert type(reply) is EnvUpdateReply
    assert reply.observation_set.tick_id == 1
    assert time() - reply.observation_set.timestamp.ToSeconds() < 1
    assert reply.observation_set.observations[0].snapshot is False

    assert reply.feedbacks[0].actor_id == 0
    assert reply.feedbacks[0].tick_id == 3
    assert reply.feedbacks[0].value == 0.5
    assert reply.feedbacks[0].confidence == 1


def test_should_cleanup_on_end(empty_env_class):
    sut = EnvService(empty_env_class, settings)
    req = env_pb.EnvStartRequest(trial_id=TRIAL_ID, actor_counts=[3, 1])
    sut.Start(req, {})

    req = env_pb.EnvEndRequest(trial_id=TRIAL_ID)

    reply = sut.End(req, {})
    assert type(reply) is EnvEndReply
    assert not bool(sut._envs)
