# from cogment import DataTypes
from cogment.client import _Connection_impl as Connection
from cogment.api.orchestrator_pb2_grpc import TrialServicer
from cogment.api.orchestrator_pb2 import (
    TrialStartReply, TrialEndReply, TrialActionReply, TrialFeedbackRequest)

import fixtures.cog_settings as settings

import pytest
from pytest import fixture
from unittest.mock import Mock, patch

import fixtures.rps_pb2 as rps_pb2


@fixture
def mock_trial_service():
    service = TrialServicer()

    assert hasattr(service, "Start")
    assert hasattr(service, "End")
    assert hasattr(service, "Action")
    assert hasattr(service, "ActionStream")
    assert hasattr(service, "GiveFeedback")
    assert hasattr(service, "Version")

    service.Start = Mock()
    service.End = Mock()
    service.Action = Mock()
    service.ActionStream = Mock()
    service.GiveFeedback = Mock()
    service.Version = Mock()

    return service


def test_connection_no_settings(mock_trial_service):
    with pytest.raises(Exception):
        Connection(mock_trial_service, None)


def test_connection_no_conn():
    with pytest.raises(Exception):
        Connection(None, settings)


def test_simple_start(mock_trial_service):
    conn = Connection(mock_trial_service, settings)

    # Establishing the connection shouldn't create a trial immediately
    mock_trial_service.Start.assert_not_called()

    # Calling start creates the trial, and returns the initial obsercation
    mock_trial_service.Start.return_value = TrialStartReply(trial_id="abc",
                                                            actor_counts=[3, 1]
                                                            )
    my_actor_class = settings.actor_classes.player

    trial = conn.start_trial(my_actor_class)

    mock_trial_service.Start.assert_called_once()
    assert mock_trial_service.GiveFeedback.call_count == 0
    assert trial.id == "abc"


def test_simple_action(mock_trial_service):
    conn = Connection(mock_trial_service, settings)

    # Calling start creates the trial, and returns the initial obsercation
    mock_trial_service.Start.return_value = TrialStartReply(trial_id="abc",
                                                            actor_counts=[3, 1]
                                                            )
    mock_trial_service.Action.return_value = TrialActionReply()

    trial = conn.start_trial(settings.actor_classes.player)

    trial.do_action(rps_pb2.ActorAction())
    trial.do_action(rps_pb2.ActorAction())
    trial.do_action(rps_pb2.ActorAction())

    mock_trial_service.Start.assert_called_once()
    assert mock_trial_service.Action.call_count == 3
    assert mock_trial_service.GiveFeedback.call_count == 0


def test_end_trial(mock_trial_service):
    conn = Connection(mock_trial_service, settings)

    # Calling start creates the trial, and returns the initial obsercation
    mock_trial_service.Start.return_value = TrialStartReply(trial_id="abc",
                                                            actor_counts=[3, 1]
                                                            )
    mock_trial_service.Action.return_value = TrialActionReply()
    mock_trial_service.End.return_value = TrialEndReply()

    trial = conn.start_trial(settings.actor_classes.player)

    trial.do_action(rps_pb2.ActorAction())
    trial.do_action(rps_pb2.ActorAction())
    trial.do_action(rps_pb2.ActorAction())

    mock_trial_service.Start.assert_called_once()
    assert mock_trial_service.Action.call_count == 3
    assert mock_trial_service.GiveFeedback.call_count == 0


@patch('cogment.client.uuid4')
def test_reward_sent_on_action(uuid4_mock, mock_trial_service):
    uuid4_mock.return_value = 'reward-send-on-action-session-id'

    conn = Connection(mock_trial_service, settings)

    # Calling start creates the trial, and returns the initial obsercation
    mock_trial_service.Start.return_value = TrialStartReply(trial_id="abc",
                                                            actor_counts=[3, 1]
                                                            )
    mock_trial_service.Action.return_value = TrialActionReply()
    mock_trial_service.End.return_value = TrialEndReply()

    trial = conn.start_trial(settings.actor_classes.player)

    trial.actors.player[0].add_feedback(tick_id=1, value=1, confidence=0)
    trial.actors.player[0].add_feedback(tick_id=2, value=2, confidence=3)

    expected_feedback_msg = TrialFeedbackRequest(trial_id="abc")
    fb = expected_feedback_msg.feedbacks.add()
    fb.actor_id = 0
    fb.tick_id = 1
    fb.value = 1
    fb.confidence = 0

    fb = expected_feedback_msg.feedbacks.add()
    fb.actor_id = 0
    fb.tick_id = 2
    fb.value = 2
    fb.confidence = 3

    trial.do_action(rps_pb2.ActorAction())

    mock_trial_service.GiveFeedback.assert_called_with(expected_feedback_msg,
                                                       metadata=(('session_id', 'reward-send-on-action-session-id'),))


@patch('cogment.client.uuid4')
def test_reward_sent_on_end(uuid4_mock, mock_trial_service):
    uuid4_mock.return_value = 'reward-send-on-end-session-id'

    conn = Connection(mock_trial_service, settings)

    # Calling start creates the trial, and returns the initial obsercation
    mock_trial_service.Start.return_value = TrialStartReply(trial_id="abc",
                                                            actor_counts=[3, 1]
                                                            )
    mock_trial_service.Action.return_value = TrialActionReply()
    mock_trial_service.End.return_value = TrialEndReply()

    trial = conn.start_trial(settings.actor_classes.player)

    trial.actors.player[0].add_feedback(tick_id=1, value=1, confidence=0)
    trial.actors.player[0].add_feedback(tick_id=2, value=2, confidence=3)

    expected_feedback_msg = TrialFeedbackRequest(trial_id="abc")
    fb = expected_feedback_msg.feedbacks.add()
    fb.actor_id = 0
    fb.tick_id = 1
    fb.value = 1
    fb.confidence = 0

    fb = expected_feedback_msg.feedbacks.add()
    fb.actor_id = 0
    fb.tick_id = 2
    fb.value = 2
    fb.confidence = 3

    trial.end()

    mock_trial_service.GiveFeedback.assert_called_with(expected_feedback_msg,
                                                       metadata=(('session_id', 'reward-send-on-end-session-id'),))
