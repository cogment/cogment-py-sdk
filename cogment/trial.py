from cogment.actor import Actor


class Trial:

    def __init__(self, id_, cog_project, trial_config):
        self.id_ = id_
        self.over = False
        self.cog_project = cog_project
        self.actors = []

    def _add_actors(self, actors_in_trial):
        for actor in actors_in_trial:
            actor_class = self.cog_project.actor_classes[actor.actor_class]
            actor = Actor(actor_class, actor.name)
            self.actors.append(actor)


# A trial, from the perspective of the lifetime manager
class TrialLifecycle(Trial):

    def __init__(self, id_, cog_project, trial_config, actor_class_idx, actor_names):
        super().__init__(id_, cog_project, trial_config)
        self._add_actors(actor_class_idx, actor_names)
