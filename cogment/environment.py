import asyncio
import importlib

class Env:
    # def __init__(self, actor_id, trial):

    def __init__(self):

        self.env_id = -1
        # self.actor_id = actor_id
        self._message = []
        # self.trial = trial
        self.name = "env"

    def send_message(self, user_data):
        self._message.append((user_data))


class EnvironmentSession:
    """This represents the environment being performed locally."""

    def __init__(self, impl, trial, impl_name):
        self.trial = trial
        self.end_trial = False
        self.impl_name = impl_name
        # Callbacks
        self.on_actions = None
        self.on_reward = None
        self.on_message = None
        self.on_trial_over = None

        self.latest_actions = None
        self.latest_reward = None
        self.latest_message = None
        self.__impl = impl
        self.__started = False
        self.__actions_future = None
        self._ignore_incoming_actions = False

    def start(self, observations):
        assert not self.__started
        self.__started = True

        self._consume_obs(observations, False)

    async def gather_actions(self):
        assert self.__started

        if self.latest_actions:
            result = self.latest_actions
            self.latest_actions = None
            return result
        
        self.__actions_future = asyncio.get_running_loop().create_future()
        return await self.__actions_future

    def produce_observations(self, observations):
        assert self.__started
        self._consume_obs(observations, False)

    def end(self, final_observations):
        self.end_trial = True
        self._consume_obs(final_observations, True)
        if self.on_trial_over:
            self.on_trial_over()

    def _new_action(self, actions):
        self.latest_actions = actions

        if self.on_actions:
            self.on_actions(actions)

        if self.__actions_future:
            self.__actions_future.set_result(actions)
            self.__actions_future = None

    def _new_message(self, message):
        self.latest_message = message

        class_type = message.payload.type_url.split('.')
        user_data = getattr(importlib.import_module(
            self.trial.cog_project.protolib), class_type[-1])()
        message.payload.Unpack(user_data)

        if self.on_message:
            self.on_message(message.sender_id, user_data)

    async def _run(self):
        await self.__impl(self, self.trial)


class _ServedEnvironmentSession(EnvironmentSession):
    """An environment session that is served from an environment service."""

    def __init__(self, impl, trial, impl_name):
        super().__init__(impl, trial, impl_name)
        self._obs_queue = asyncio.Queue()

    # maybe needs to be consume observation
    def _consume_obs(self, observations, final):
        self._obs_queue.put_nowait((observations, final))
