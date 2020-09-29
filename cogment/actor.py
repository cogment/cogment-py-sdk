import asyncio
import importlib


class Actor:

    def __init__(self, actor_class, name):
        self.actor_class = actor_class
        self.name = name

        self._feedback = []
        self._message = []

    def add_feedback(self, value=None, confidence=None, tick_id=None, user_data=None):
        if tick_id is None:
            tick_id = -1

        self._feedback.append((tick_id, value, confidence, user_data))

    def send_message(self, user_data=None):
        self._message.append(user_data)


class ActorClass:

    def __init__(self, id_, config_type, action_space, observation_space,
                 observation_delta, observation_delta_apply_fn, feedback_space):
        self.id_ = id_
        self.config_type = config_type
        self.action_space = action_space
        self.observation_space = observation_space
        self.observation_delta = observation_delta
        self.observation_delta_apply_fn = observation_delta_apply_fn
        self.feedback_space = feedback_space


class ActorClassList:

    def __init__(self, *args):
        self._actor_classes_list = list(args)

        for a_c in args:
            setattr(self, a_c.id_, a_c)

    def __iter__(self):
        return iter(self._actor_classes_list)

    def __contains__(self, key):
        return hasattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    def get_class_by_index(self, index):
        return self._actor_classes_list[index]


class ActorSession:
    """This represents an actor being performed locally."""

    def __init__(self, impl, actor_class, trial, name, impl_name):
        self.actor_class = actor_class
        self.trial = trial
        self.name = name
        self.end_trial = False
        self.impl_name = impl_name
        # Callbacks
        self.on_observation = None
        self.on_reward = None
        self.on_message = None
        self.on_trial_over = None

        self.latest_observation = None
        self.latest_reward = None
        self.latest_message = None
        self.__impl = impl
        self.__started = False
        self.__obs_future = None

    async def start(self):
        assert not self.__started
        self.__started = True

        # We may have already received an observation
        if self.latest_observation:
            return self.latest_observation

        # Wait until the initial observation is available
        self.__obs_future = asyncio.get_running_loop().create_future()
        return await self.__obs_future

    async def end(self):
        self.end_trial = True
        if self.on_trial_over:
            self.on_trial_over()

    def start_nowait(self):
        assert not self.__started
        self.__started = True

    async def do_action(self, action):
        assert self.__started

        self.__obs_future = asyncio.get_running_loop().create_future()
        await self._consume_action(action)

        return await self.__obs_future

    def do_action_nowait(self, action):
        assert self.__started

        self._consume_action(action)

    def _new_observation(self, obs, final):
        self.trial.over = final

        self.latest_observation = obs

        if self.on_observation:
            self.on_observation(obs)

        if self.__obs_future:
            self.__obs_future.set_result(obs)

    def _new_reward(self, reward):
        self.latest_reward = reward

        if self.on_reward:
            self.on_reward(reward)

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


class _ServedActorSession(ActorSession):
    """An actor session that is served from an agent service."""

    def __init__(self, impl, actor_class, trial, name, impl_name):
        super().__init__(impl, actor_class, trial, name, impl_name)
        self._action_queue = asyncio.Queue()

    async def _consume_action(self, action):
        await self._action_queue.put(action)
