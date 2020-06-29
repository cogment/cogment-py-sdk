# from cogment import DataTypes
from cogment.agent_service import (Agent, AgentService, AgentStartReply,
                                   AgentRewardReply, AgentEndReply)
# from datetime import datetime
# from time import time
# from types import SimpleNamespace
# from cogment import ActorClass

import cogment.api.common_pb2 as common_pb
import cogment.api.agent_pb2 as agent_pb
import pytest
import fixtures.rps_pb2 as rps_pb2

import fixtures.cog_settings as settings

TRIAL_ID = "12345"


# types_no_config = DataTypes()
# types_with_config = DataTypes(env_config=common_pb.VersionInfo)


class AgentClass(Agent):

    actor_class = settings.actor_classes.player

    def reward(self, reward):
        pass

    def decide(self, observation):
        if observation.p1_score == 10:
            return self.actor_class.action_space(decision=rps_pb2.ROCK)

        return self.actor_class.action_space(decision=rps_pb2.PAPER)


@pytest.fixture
def agent_class():
    return AgentClass


def test_should_raise_if_agent_not_Agent():
    class AgentWithoutInheritance():
        pass

    with pytest.raises(AssertionError):
        AgentService(AgentWithoutInheritance, {})


def test_should_raise_if_agent_doesnt_have_actor_class():
    class MyAgent(Agent):
        pass

    with pytest.raises(AttributeError):
        AgentService(MyAgent, {})


def test_should_raise_with_trial_id_empty(agent_class):
    sut = AgentService(agent_class, settings)
    req = agent_pb.AgentStartRequest(trial_id="", actor_id=0)

    with pytest.raises(Exception, match=r"No trial_id provided"):
        sut.Start(req, {})


def test_should_return_AgentStartReply(agent_class):
    sut = AgentService(agent_class, settings)
    req = agent_pb.AgentStartRequest(trial_id=TRIAL_ID,
                                     actor_id=0,
                                     actor_counts=[1, 1])

    reply = sut.Start(req, {})

    assert type(reply) is AgentStartReply


def test_should_catch_exception_on_agent_init():
    class MyAgent(AgentClass):
        def __init__(self, trial, actor, config):
            raise Exception("raise in init")

    sut = AgentService(MyAgent, settings)
    req = agent_pb.AgentStartRequest(trial_id=TRIAL_ID,
                                     actor_id=0,
                                     actor_counts=[1, 1])

    with pytest.raises(Exception, match=r"raise in init"):
        sut.Start(req, {})


def test_should_have_correct_actor_id():
    class MyPlayerAgent(AgentClass):
        actor_class = settings.actor_classes.player

        def __init__(self, trial, actor, config):
            super().__init__(trial, actor, config)
            assert self.actor_id == 1
            assert self.id_in_class == 1

    class MyJudgeAgent(AgentClass):
        actor_class = settings.actor_classes.judge

        def __init__(self, trial, actor, config):
            super().__init__(trial, actor, config)
            assert self.actor_id == 3
            assert self.id_in_class == 0

    sut = AgentService(MyPlayerAgent, settings)
    req = agent_pb.AgentStartRequest(trial_id=TRIAL_ID, actor_id=1, actor_counts=[3, 1])
    sut.Start(req, {})

    sut2 = AgentService(MyJudgeAgent, settings)
    req2 = agent_pb.AgentStartRequest(trial_id=TRIAL_ID, actor_id=3, actor_counts=[3, 1])
    sut2.Start(req2, {})


def test_should_raise_on_decide_when_trial_doesnt_exist(agent_class):
    sut = AgentService(agent_class, settings)

    observation = common_pb.Observation(
        tick_id=123,
        data=common_pb.ObservationData(
            content="".encode(),
            snapshot=True
        )
    )
    observation.timestamp.GetCurrentTime()

    req = agent_pb.AgentDecideRequest(trial_id=TRIAL_ID, actor_id=0, observation=observation)

    with pytest.raises(Exception, match=r"trial does not exists"):
        sut.Decide(req, {})


def test_should_return_AgentDecideReply(agent_class):
    sut = AgentService(agent_class, settings)
    req = agent_pb.AgentStartRequest(trial_id=TRIAL_ID, actor_id=0, actor_counts=[1, 1])
    sut.Start(req, {})

    observation = common_pb.Observation(
        tick_id=123,
        data=common_pb.ObservationData(
            content=rps_pb2.GameState(p1_score=10).SerializeToString(),
            snapshot=True
        )
    )
    observation.timestamp.GetCurrentTime()

    req = agent_pb.AgentDecideRequest(trial_id=TRIAL_ID, actor_id=0, observation=observation)

    reply = sut.Decide(req, {})

    aa = rps_pb2.ActorAction()
    aa.ParseFromString(reply.action.content)

    assert aa.decision == rps_pb2.ROCK

    observation = common_pb.Observation(
        tick_id=123,
        data=common_pb.ObservationData(
            content=rps_pb2.GameState(p1_score=9).SerializeToString(),
            snapshot=True
        )
    )
    observation.timestamp.GetCurrentTime()

    req = agent_pb.AgentDecideRequest(trial_id=TRIAL_ID, actor_id=0, observation=observation)

    reply = sut.Decide(req, {})

    aa = rps_pb2.ActorAction()
    aa.ParseFromString(reply.action.content)

    assert aa.decision == rps_pb2.PAPER


def test_should_raise_on_reward_when_trial_doesnt_exist(agent_class):
    sut = AgentService(agent_class, settings)

    req = agent_pb.AgentRewardRequest(trial_id=TRIAL_ID, actor_id=0)

    with pytest.raises(Exception, match=r"trial does not exists"):
        sut.Reward(req, {})


def test_should_return_RewardStartReply(agent_class):
    sut = AgentService(agent_class, settings)
    req = agent_pb.AgentStartRequest(trial_id=TRIAL_ID, actor_id=0, actor_counts=[1, 1])
    sut.Start(req, {})

    req = agent_pb.AgentRewardRequest(trial_id=TRIAL_ID, actor_id=0)

    reply = sut.Reward(req, {})

    assert type(reply) is AgentRewardReply


def test_should_cleanup_on_end(agent_class):
    sut = AgentService(agent_class, settings)
    req = agent_pb.AgentStartRequest(trial_id=TRIAL_ID, actor_id=0, actor_counts=[1, 1])
    sut.Start(req, {})

    req = agent_pb.AgentEndRequest(trial_id=TRIAL_ID, actor_id=0)

    reply = sut.End(req, {})

    assert type(reply) is AgentEndReply

    assert not bool(sut._agents)
