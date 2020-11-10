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
    trial._add_env()
    return trial


class TestTrial:
    def test_get_receivers_all(self, trial):
        receivers = trial.get_receivers(pattern="*", env=True)
        assert len(receivers) == 5
        assert receivers[0].name == "agent_1"
        assert receivers[1].name == "agent_2"
        assert receivers[2].name == "agent_3"
        assert receivers[3].name == "agent_4"
        assert isinstance(receivers[4], Environment)

    def test_get_receivers_all_actors(self, trial):
        receivers = trial.get_receivers(pattern="*.*")
        assert len(receivers) == 4
        assert receivers[0].name == "agent_1"
        assert receivers[1].name == "agent_2"
        assert receivers[2].name == "agent_3"
        assert receivers[3].name == "agent_4"

    def test_get_receivers_by_exact_name(self, trial):
        receivers = trial.get_receivers(pattern=["agent_3", "agent_2"])
        assert len(receivers) == 2
        assert receivers[0].name == "agent_3"
        assert receivers[1].name == "agent_2"

    def test_get_receivers_by_class(self, trial):
        receivers = trial.get_receivers(pattern="my_agent_class_1.*")
        assert len(receivers) == 2
        assert receivers[0].name == "agent_1"
        assert receivers[1].name == "agent_3"

    def test_get_receivers_by_index(self, trial):
        receivers_a = trial.get_receivers(pattern=0)
        assert len(receivers_a) == 1
        assert receivers_a[0].name == "agent_1"

        receivers_b = trial.get_receivers(pattern=1)
        assert len(receivers_b) == 1
        assert receivers_b[0].name == "agent_2"

        receivers_c = trial.get_receivers(pattern=4)
        assert len(receivers_c) == 0
