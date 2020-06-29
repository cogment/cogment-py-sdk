from cogment.actor_class import ActorClass


# This is the default delta application function that is used when the
# Observation space and Observation delta of an actor is class is of the same
# type
def _apply_delta_replace(observation, delta):
    assert type(observation) == type(delta)
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
