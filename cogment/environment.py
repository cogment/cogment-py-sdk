import asyncio
import importlib


class EnvClass:

    def __init__(self, id_, config_type):
        self.id_ = id_
        self.config_type = config_type


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

    def __init__(self, impl, actor_class, trial, impl_name):
        self.actor_class = actor_class
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

    async def start(self, observations):
        assert not self.__started
        self.__started = True

        await self._consume_obs(observations)

    async def update(self, observations):

        assert self.__started

        self.__actions_future = asyncio.get_running_loop().create_future()

        await self._consume_obs(observations)

        return await self.__actions_future

    async def end(self):
        self.end_trial = True
        if self.on_trial_over:
            self.on_trial_over()

    def _new_action(self, actions):
        self.latest_actions = actions

        if self.on_actions:
            self.on_actions(actions)

        if self.__actions_future:
            self.__actions_future.set_result(actions)

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

    def __init__(self, impl, env_class, trial, impl_name):
        super().__init__(impl, env_class, trial, impl_name)
        self._obs_queue = asyncio.Queue()

    # maybe needs to be consume observation
    async def _consume_obs(self, observations):
        await self._obs_queue.put(observations)
