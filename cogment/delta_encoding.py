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

from cogment.actor import ActorClass
import logging


# This is the default delta application function that is used when the
# Observation space and Observation delta of an actor is a class of the same type
def _apply_delta_replace(observation, delta):
    if type(observation) != type(delta):
        logging.error(f"Unexpected type difference for observation [{type(observation)}] and delta [{type(delta)}]")
    return delta


# Correctly updates or creates an observation based on the data contained in a
# cogment.api.common_pb2.ObservationData
def DecodeObservationData(actor_class: ActorClass, data, previous_observation=None):
    if not previous_observation:
        previous_observation = actor_class.observation_space()

    if data.snapshot:
        previous_observation.ParseFromString(data.content)
        return previous_observation
    else:
        delta = actor_class.observation_delta()
        delta.ParseFromString(data.content)
        apply_fn = actor_class.observation_delta_apply_fn
        return apply_fn(previous_observation, delta)
