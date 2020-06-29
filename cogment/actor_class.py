class ActorClass:
    def __init__(self, id, config_type, action_space, observation_space,
                 observation_delta, observation_delta_apply_fn, feedback_space):
        self.id = id
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
            setattr(self, a_c.id, a_c)

    def __iter__(self):
        return iter(self._actor_classes_list)

    def get_actor_counts(self, trial_params):
        result = [0] * len(self._actor_classes_list)

        index_map = {}
        for index, actor_class in enumerate(self._actor_classes_list):
            index_map[actor_class.id] = index

        for actor in trial_params.actors:
            result[index_map[actor.actor_class]] += 1

        return result
