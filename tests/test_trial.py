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

from cogment.actor import Actor
from cogment.api.common_pb2 import TrialActor
from cogment.environment import Environment
from cogment.trial import Trial

from test_cogment_app import cog_settings
from test_cogment_app.data_pb2 import EnvConfig, TrialConfig


@pytest.fixture(scope="function")
def trial():
    # Mimicking what's done by EnvironmentServicer::OnStart, it seems like the most complete example
    actors = [
             TrialActor(actor_class="my_agent_class_1", name="agent_1"),
             TrialActor(actor_class="my_agent_class_2", name="agent_2"),
             TrialActor(actor_class="my_agent_class_1", name="agent_3"),
             TrialActor(actor_class="my_agent_class_2", name="agent_4"),
             ]
    trial = Trial("test", actors, cog_settings)
    return trial


class TestTrial:
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
        actors = trial.get_actors(["my_agent_class_1.*"])
        assert len(actors) == 2
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_class_and_by_name1(self, trial):
        actors = trial.get_actors(["my_agent_class_1.*", "agent_1"])
        assert len(actors) == 2
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_class_and_by_name2(self, trial):
        actors = trial.get_actors(["my_agent_class_1.*", "agent_2"])
        assert len(actors) == 3
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_2"
        assert actors[2].name == "agent_3"
