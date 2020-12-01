# Copyright 2020 Artificial Intelligence Redefined <dev+cogment@ai-r.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
import unittest

from cogment.actor import Actor
from cogment.api.common_pb2 import TrialActor
from cogment.environment import Environment
from cogment.api.common_pb2 import Message, TrialActor
from cogment.errors import Error
from cogment.trial import Trial

# Works because the `test_cogment_app` directory is added to sys.path in conftest.py
import cog_settings
from data_pb2 import EnvConfig, TrialConfig, MyMessageUserData

@pytest.fixture(scope="function")
def unittest_case():
    return unittest.TestCase()

@pytest.fixture(scope="function")
def trial():
    # Mimicking what's done by EnvironmentServicer::OnStart, it seems like the most complete example
    actors = [
             TrialActor(actor_class="my_actor_class_1", name="agent_1"),
             TrialActor(actor_class="my_actor_class_2", name="agent_2"),
             TrialActor(actor_class="my_actor_class_1", name="agent_3"),
             TrialActor(actor_class="my_actor_class_2", name="agent_4"),
             ]
    trial = Trial("test", actors, cog_settings)
    return trial


class TestTrial:
    def test_add_actor_with_unknown_class(self):
        with pytest.raises(Error):
            Trial("test_add_actor_with_unknown_class", [
                TrialActor(actor_class="my_actor_class_1", name="agent_1"),
                TrialActor(actor_class="my_unknown_actor_class", name="agent_2")
            ], cog_settings)

    def test_get_environment(self, trial):
        assert isinstance(trial.get_environment(), Environment)

    def test_get_actors_all(self, trial):
        actors = trial.get_actors(["*"])
        assert len(actors) == 4
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_2"
        assert actors[2].name == "agent_3"
        assert actors[3].name == "agent_4"

    def test_get_actors_one(self, trial):
        actors = trial.get_actors(["agent_2"])
        assert len(actors) == 1
        assert actors[0].name == "agent_2"

    def test_get_actors_many(self, trial):
        actors = trial.get_actors(["agent_3", "agent_2"])
        assert len(actors) == 2
        assert actors[0].name == "agent_2"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_class(self, trial):
        actors = trial.get_actors(["my_actor_class_1.*"])
        assert len(actors) == 2
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_class_and_by_name1(self, trial):
        actors = trial.get_actors(["my_actor_class_1.*", "agent_1"])
        assert len(actors) == 2
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_class_and_by_name2(self, trial):
        actors = trial.get_actors(["my_actor_class_1.*", "agent_2"])
        assert len(actors) == 3
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_2"
        assert actors[2].name == "agent_3"

    def test_send_messages(self, trial, unittest_case):
        trial.send_message(MyMessageUserData(a_string="foo", an_int=42), to=["agent_3", "agent_2"])
        trial.send_message(MyMessageUserData(a_string="bar", an_int=32), to=["agent_1", "agent_3"])
        trial.send_message(MyMessageUserData(a_string="baz", an_int=29), to_environment=True)

        messages_as_tuples = []
        for m in trial._gather_all_messages("test_source"):
            payload = MyMessageUserData()
            assert m.payload.Unpack(payload)
            messages_as_tuples.append((m.sender_name, m.receiver_name, payload))

        assert len(messages_as_tuples) == 5
        unittest_case.assertCountEqual(messages_as_tuples, [
            ("test_source", "agent_2", MyMessageUserData(a_string="foo", an_int=42)),
            ("test_source", "agent_3", MyMessageUserData(a_string="foo", an_int=42)),
            ("test_source", "agent_1", MyMessageUserData(a_string="bar", an_int=32)),
            ("test_source", "agent_3", MyMessageUserData(a_string="bar", an_int=32)),
            ("test_source", "env", MyMessageUserData(a_string="baz", an_int=29))
        ])

        assert len([m for m in trial._gather_all_messages("test_source")]) == 0

    def test_send_messages_bad_payload(self, trial):
        trial.send_message({"a_string": "foo", "an_int": 42}, to=["agent_3", "agent_2"])

        # Maybe this should be caught earlier
        with pytest.raises(AttributeError):
            [m for m in trial._gather_all_messages("test_source")]


