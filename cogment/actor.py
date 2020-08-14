import asyncio


class Actor:

    def __init__(self, actor_class, name):
        self.actor_class = actor_class
        self.name = name


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

    def __init__(self, impl, actor_class, trial, name):
        self.actor_class = actor_class
        self.trial = trial
        self.name = name
        # Callbacks
        self.on_observation = None
        self.on_reward = None
        self.on_message = None
        self.on_trial_over = None

        self.latest_observation = None
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

    def start_nowait(self):
        assert not self.__started
        self.__started = True

    async def do_action(self, action):
        assert self.__started

        self.__obs_future = asyncio.get_running_loop().create_future()
        await self._consume_action(action)

        # Wait until the next observation is available
        #
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

    async def _run(self):
        await self.__impl(self, self.trial)


class _ServedActorSession(ActorSession):
    """An actor session that is served from an agent service."""

    def __init__(self, impl, actor_class, trial, name):
        super().__init__(impl, actor_class, trial, name)
        self._action_queue = asyncio.Queue()

    async def _consume_action(self, action):
        await self._action_queue.put(action)
