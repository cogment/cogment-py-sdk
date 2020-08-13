from cogment.actor import Actor


class Trial:

    def __init__(self, id_, cog_project, trial_config):
        self.id_ = id_
        self.over = False
        self.cog_project = cog_project
        self.actors = []

    def _add_actors(self, actor_class_idx, actor_names):
        assert len(actor_class_idx) == len(actor_names)
        for i, name in enumerate(actor_names):
            actor_class = self.cog_project.actor_classes.get_class_by_index(actor_class_idx[
                                                                            i])
            actor = Actor(actor_class, name)
            self.actors.append(actor)


# A trial, from the perspective of the lifetime manager
class TrialLifecycle(Trial):

    def __init__(self, id_, cog_project, trial_config, actor_class_idx, actor_names):
        super().__init__(id_, cog_project, trial_config)
        self._add_actors(actor_class_idx, actor_names)
