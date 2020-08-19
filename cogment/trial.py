from cogment.actor import Actor
from cogment.api.common_pb2 import Feedback


class Trial:

    def __init__(self, id_, cog_project, trial_config):
        self.id_ = id_
        self.over = False
        self.cog_project = cog_project
        self.actors = []

        self.__actor_by_name = {}

    def _add_actors(self, actors_in_trial):

        for actor in actors_in_trial:
            actor_class = self.cog_project.actor_classes[actor.actor_class]
            actor = Actor(actor_class, actor.name)
            self.actors.append(actor)

    def get_actors(self, pattern):
        if isinstance(pattern, int) or isinstance(pattern, str):
            pattern_list = [pattern]
        elif isinstance(pattern, list):
            pattern_list = pattern
        actor_fdbk_list = []
        for target in pattern_list:
            for actor_index, actor in enumerate(self.actors):
                if target == "*" or target == "*.*":
                    actor_fdbk_list.append(actor)
                elif isinstance(target, int):
                    if actor_index == target:
                        actor_fdbk_list.append(actor)
                elif isinstance(target, str):
                    if "." not in target:
                        if actor.name == target:
                            actor_fdbk_list.append(actor)
                    else:
                        class_name = target.split(".")
                        if class_name[1] == actor.name:
                            actor_fdbk_list.append(actor)
                        elif class_name[1] == "*":
                            if actor.actor_class.id_ == class_name[0]:
                                actor_fdbk_list.append(actor)

        return actor_fdbk_list

    def add_feedback(self, to, value, confidence):
        for d in self.get_actors(pattern=to):
            d.add_feedback(value=value, confidence = confidence)

    def _gather_all_feedback(self):
        for actor_index, actor in enumerate(self.actors):
            a_fb = actor._feedback
            actor._feedback = []

            for fb in a_fb:
                re = Feedback(
                    actor_id=actor_index,
                    tick_id=fb[0],
                    value=fb[1],
                    confidence=fb[2]
                )
                if fb[3] is not None:
                    re.content = fb[3].SerializeToString()

                yield re


# A trial, from the perspective of the lifetime manager
class TrialLifecycle(Trial):

    def __init__(self, id_, cog_project, trial_config, actor_class_idx, actor_names):
        super().__init__(id_, cog_project, trial_config)
        self._add_actors(actor_class_idx, actor_names)
