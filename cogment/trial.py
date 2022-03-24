# Copyright 2021 AI Redefined Inc. <dev+cogment@ai-r.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from cogment.errors import CogmentError


class Trial:
    """Internal class maintaining the information of a trial."""

    class Actor:
        """Internal class maintaining the information of an actor in a trial."""
        def __init__(self, name, actor_class):
            self.name = name
            self.actor_class = actor_class

    def __init__(self, id, actors_in_trial, cog_settings):
        self.id = id
        self.ended = False
        self.ending = False
        self.ending_ack = False
        self.cog_settings = cog_settings
        self.tick_id = -1

        self.actors = []
        for actor in actors_in_trial:
            if actor.actor_class not in self.cog_settings.actor_classes:
                raise CogmentError(f"class [{actor.actor_class}] of actor [{actor.name}] cannot be found.")
            actor_class = self.cog_settings.actor_classes[actor.actor_class]
            new_actor = self.Actor(name=actor.name, actor_class=actor_class)
            self.actors.append(new_actor)

    def __str__(self):
        result = f"Trial: id = {self.id}, tick_id = {self.tick_id}, ended = {self.ended}"
        result += f", actors = "
        for actor in self.actors:
            result += f"{{name = {actor.name}, class = {actor.actor_class.name}}},"
        return result
