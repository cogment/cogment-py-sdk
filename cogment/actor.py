from asyncio import Queue

class ActorSession:
    """This represents an actor being performed locally."""
    def __init__(self, impl, actor_class):
        self.actor_class = actor_class
        self.on_observation = None
        self.on_reward = None
        self.on_message = None
        self.on_trial_over = None
        
        self.__impl = __impl
        self.__started = False
        self.__action_queue = Queue()
        self.__observation_queue = Queue()

    def start(self):
        assert not self.__started
  
        self.__started = True

    def start_async(self):
        assert not self.__started
  
        self.__started = True

    def do_action(self, action):
        assert self.__started
        self.__action_queue.put(action)

    def __receive_observation(self, obs):
        self.__observation_queue.put(obs)


class __ServedActorSession(ActorSession):
    """An actor session that is served from an agent service."""
    def __init__(self, impl, actor_class):
        pass
        