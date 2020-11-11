import pytest

from cogment.actor import Actor
from cogment.api.common_pb2 import TrialActor
from cogment.client import Connection
from cogment.environment import Environment
from cogment.trial import Trial

from test_cogment_app import cog_settings
from test_cogment_app.data_pb2 import EnvConfig, TrialConfig


@pytest.fixture(scope="module")
def trial():
    # Mimicking what's done by EnvironmentServicer::Start, it seems like the most complete example
    trial = Trial(
        id_="test",
        cog_project=cog_settings,
        trial_config=TrialConfig(env_config=EnvConfig()),
    )
    trial._add_actors(
        [
            TrialActor(actor_class="my_agent_class_1", name="agent_1"),
            TrialActor(actor_class="my_agent_class_2", name="agent_2"),
            TrialActor(actor_class="my_agent_class_1", name="agent_3"),
            TrialActor(actor_class="my_agent_class_2", name="agent_4"),
        ]
    )
    trial._add_actor_counts()
    trial._add_environment()
    return trial


class TestTrial:
    def test_get_environment(self, trial):
        assert isinstance(trial.get_environment(), Environment)

    def test_get_actors_all(self, trial):
        actors = trial.get_actors(pattern="*")
        assert len(actors) == 4
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_2"
        assert actors[2].name == "agent_3"
        assert actors[3].name == "agent_4"

    def test_get_actors_all_alt(self, trial):
        actors = trial.get_actors(pattern="*.*")
        assert len(actors) == 4
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_2"
        assert actors[2].name == "agent_3"
        assert actors[3].name == "agent_4"

    def test_get_actors_by_exact_name(self, trial):
        actors = trial.get_actors(pattern=["agent_3", "agent_2"])
        assert len(actors) == 2
        assert actors[0].name == "agent_2"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_class(self, trial):
        actors = trial.get_actors(pattern="my_agent_class_1.*")
        assert len(actors) == 2
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_class_and_by_name(self, trial):
        actors = trial.get_actors(pattern=["my_agent_class_1.*", "agent_1"])
        assert len(actors) == 2
        assert actors[0].name == "agent_1"
        assert actors[1].name == "agent_3"

    def test_get_actors_by_index(self, trial):
        actors_a = trial.get_actors(pattern=0)
        assert len(actors_a) == 1
        assert actors_a[0].name == "agent_1"

        actors_b = trial.get_actors(pattern=1)
        assert len(actors_b) == 1
        assert actors_b[0].name == "agent_2"

        actors_c = trial.get_actors(pattern=4)
        assert len(actors_c) == 0
