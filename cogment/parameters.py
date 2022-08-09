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

import cogment.api.common_pb2 as common_api

from cogment.errors import CogmentError
from cogment.utils import logger


class ActorParameters:
    """Class wrapping the trial api parameters for an actor"""

    def __init__(self, cog_settings, class_name, **kwargs):
        # Done not to waste resources for internal use with a '_set' call
        if cog_settings is not None:
            self._cog_settings = cog_settings
            self._raw_params = common_api.ActorParams()

            if class_name is None:
                raise CogmentError(f"Required attribute 'class_name' missing")
            if type(class_name) is not str:
                raise CogmentError(f"Wrong type for 'class_name' [{type(class_name)}]")
            self._raw_params.actor_class = class_name

            # Provide an easy way for users to set parameter attributes on construction
            for name, value in kwargs.items():
                if name[0] == "_" or name not in dir(self):
                    raise CogmentError(f"Unknown attribute [{name}]")
                setattr(self, name, value)

    def _set(self, cog_settings, raw_params):
        self._cog_settings = cog_settings
        self._raw_params = raw_params

    def __str__(self):
        result = f"ActorParameters: {self._raw_params}"
        return result

    # ----------------- properties -------------------

    @property
    def config(self):
        """Config sent to actor on trial start"""
        if self._raw_params.HasField("config"):
            config_instance = self._actor_class.config_type()
            config_instance.ParseFromString(self._raw_params.config.content)
        else:
            config_instance = None

        return config_instance

    @config.setter
    def config(self, val):
        if val is None:
            self._raw_params.ClearField("config")
        elif type(val) is self._actor_class.config_type:
            self._raw_params.config.content = val.SerializeToString()
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def class_name(self):
        """Name of the actor class"""
        return self._raw_params.actor_class

    @class_name.setter
    def class_name(self, val):
        # We could make a setter, but we would have to sync with the config and default_action: not worth it.
        raise CogmentError(f"Cannot change class name of existing instance of ActorParameters")

    @property
    def name(self):
        """Name of the actor"""
        return self._raw_params.name

    @name.setter
    def name(self, val):
        if val is None:
            self._raw_params.ClearField("name")
        elif type(val) is str:
            self._raw_params.name = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def endpoint(self):
        """Endpoint for the actor service"""
        return self._raw_params.endpoint

    @endpoint.setter
    def endpoint(self, val):
        if val is None:
            self._raw_params.ClearField("endpoint")
        elif type(val) is str:
            self._raw_params.endpoint = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def implementation(self):
        """Implementation name of the actor service"""
        return self._raw_params.implementation

    @implementation.setter
    def implementation(self, val):
        if val is None:
            self._raw_params.ClearField("implementation")
        elif type(val) is str:
            self._raw_params.implementation = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def initial_connection_timeout(self):
        """Timeout for connecting to a new trial"""
        return self._raw_params.initial_connection_timeout

    @initial_connection_timeout.setter
    def initial_connection_timeout(self, val):
        if val is None:
            self._raw_params.ClearField("initial_connection_timeout")
        else:
            self._raw_params.initial_connection_timeout = float(val)

    @property
    def response_timeout(self):
        """Timeout for response to observation"""
        return self._raw_params.response_timeout

    @response_timeout.setter
    def response_timeout(self, val):
        if val is None:
            self._raw_params.ClearField("response_timeout")
        else:
            self._raw_params.response_timeout = float(val)

    @property
    def optional(self):
        """If the actor is optional for the trial"""
        return self._raw_params.optional

    @optional.setter
    def optional(self, val):
        if val is None:
            self._raw_params.ClearField("optional")
        elif type(val) is bool:
            self._raw_params.optional = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def default_action(self):
        """The default action space for optional actors not connected"""
        if self._raw_params.HasField("default_action"):
            action_space = self._actor_class.action_space()
            action_space.ParseFromString(self._raw_params.default_action.content)
        else:
            action_space = None

        return action_space

    @default_action.setter
    def default_action(self, val):
        if val is None:
            self._raw_params.ClearField("default_action")
        elif type(val) is self._actor_class.action_space:
            self._raw_params.default_action.content = val.SerializeToString()
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def _actor_class(self):
        return getattr(self._cog_settings.actor_classes, self._raw_params.actor_class)


class _ActorsList:
    """List like object to manage actor parameters"""

    def __init__(self, cog_settings, raw_params):
        self._cog_settings = cog_settings
        self._raw_params = raw_params

    def __str__(self):
        result = f"Actors Parameters: {self._raw_params.actors}"
        return result

    def __len__(self):
        return len(self._raw_params.actors)

    def __getitem__(self, key):
        if type(key) is int:
            actor_params = ActorParameters(None, None)
            actor_params._set(self._cog_settings, self._raw_params.actors[key])
        elif type(key) is slice:
            actor_params = []
            actors = self._raw_params.actors
            for actual_index in range(len(actors))[key]:
                params = ActorParameters(None, None)
                params._set(self._cog_settings, actors[actual_index])
                actor_params.append(params)
        else:
            raise CogmentError(f"Wrong key type [{type(key)}]")

        return actor_params

    def __setitem__(self, key, val):
        if type(key) is int and type(val) is ActorParameters:
            self._raw_params.actors[key].CopyFrom(val._raw_params)
        elif type(key) is slice:
            # Complicated for very little gain
            raise CogmentError(f"Slices are not valid for setting")
        else:
            raise CogmentError(f"Wrong type [{type(key)}] [{type(val)}]")

    def __delitem__(self, key):
        del self._raw_params.actors[key]

    def __iter__(self):
        for raw_actor in self._raw_params.actors:
            actor_params = ActorParameters(None, None)
            actor_params._set(self._cog_settings, raw_actor)
            yield actor_params

    def append(self, val):
        if type(val) is ActorParameters:
            self._raw_params.actors.append(val._raw_params)
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    def extend(self, val):
        raw_list = []
        for actor in val:
            if type(actor) is not ActorParameters:
                raise CogmentError(f"Wrong type [{type(actor)}]")
            raw_list.append(actor._raw_params)

        self._raw_params.actors.extend(raw_list)

    def clear(self):
        self._raw_params.ClearField("actors")


class TrialParameters:
    """Class wrapping the api parameters of a trial"""

    _SERIALIZATION_TYPE = 2
    _METHODS = ["get_serialization_type", "serialize", "deserialize"]

    def __init__(self, cog_settings, **kwargs):
        # Done not to waste resources for internal use with a '_set' call
        if cog_settings is not None:
            self._cog_settings = cog_settings
            self._raw_params = common_api.TrialParams()
            self._actors = _ActorsList(cog_settings, self._raw_params)

            # Provide an easy way for users to set parameter attributes on construction
            for name, value in kwargs.items():
                # TODO: We could also protect the methods
                if name[0] == "_" or name in self._METHODS or name not in dir(self):
                    raise CogmentError(f"Unknown attribute [{name}]")
                setattr(self, name, value)

    def _set(self, cog_settings, raw_params):
        self._cog_settings = cog_settings
        self._raw_params = raw_params
        self._actors = _ActorsList(cog_settings, raw_params)

    def __str__(self):
        result = f"TrialParameters: {self._raw_params}"
        return result

    # Type of serialized data being produced and consumed by this class.
    # This is dependent on all the underlying protobuf messages used to
    # serialize/deserialize, and should be incremented if any of them changes in
    # a backward or forward incompatible way.
    # Current dependencies: TrialParams, DatalogParams, EnvironmentParams, ActorParams,
    #                       SerializedMessage
    def get_serialization_type(self):
        return TrialParameters._SERIALIZATION_TYPE

    def serialize(self):
        return self._raw_params.SerializeToString()

    def deserialize(self, raw_string, type=None):
        if type is not None and type != TrialParameters._SERIALIZATION_TYPE:
            raise CogmentError(f"Unknown serialization type")

        params = common_api.TrialParams()
        params.ParseFromString(raw_string)

        self._raw_params = params
        self._actors = _ActorsList(self._cog_settings, params)

    # ----------------- properties -------------------

    # Trial
    @property
    def config(self):
        """Config for initial trial setup by pre-trial hooks"""
        if self._raw_params.HasField("trial_config"):
            config_instance = self._cog_settings.trial.config_type()
            config_instance.ParseFromString(self._raw_params.trial_config.content)
        else:
            config_instance = None

        return config_instance

    @config.setter
    def config(self, val):
        if val is None:
            self._raw_params.ClearField("trial_config")

        elif isinstance(val, self._cog_settings.trial.config_type):
            self._raw_params.trial_config.content = val.SerializeToString()

        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def max_steps(self):
        """Maximum number of steps before stopping the trial"""
        return self._raw_params.max_steps

    @max_steps.setter
    def max_steps(self, val):
        if val is None:
            self._raw_params.ClearField("max_steps")
        elif type(val) is int:
            self._raw_params.max_steps = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def max_inactivity(self):
        """Maximum amount of time (in seconds) of inactivity before a trial is terminated"""
        return self._raw_params.max_inactivity

    @max_inactivity.setter
    def max_inactivity(self, val):
        if val is None:
            self._raw_params.ClearField("max_inactivity")
        elif type(val) is int:
            self._raw_params.max_inactivity = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def nb_buffered_ticks(self):
        """Nb of buffered ticks before samples are sent to the datalog"""
        return self._raw_params.nb_buffered_ticks

    @nb_buffered_ticks.setter
    def nb_buffered_ticks(self, val):
        if val is None:
            self._raw_params.ClearField("nb_buffered_ticks")
        elif type(val) is int:
            self._raw_params.nb_buffered_ticks = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    # Datalog
    @property
    def datalog_endpoint(self):
        """Endpoint for the datalog service"""
        return self._raw_params.datalog.endpoint

    @datalog_endpoint.setter
    def datalog_endpoint(self, val):
        if val is None:
            self._raw_params.datalog.ClearField("endpoint")
        elif type(val) is str:
            self._raw_params.datalog.endpoint = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def datalog_exclude_fields(self):
        """Name of fields to exclude from the data sent to the datalog"""
        return tuple(field for field in self._raw_params.datalog.exclude_fields)

    @datalog_exclude_fields.setter
    def datalog_exclude_fields(self, val):
        if val is None:
            self._raw_params.datalog.ClearField("exclude_fields")
        else:
            raw_fields = []
            for field in val:
                if type(field) is not str:
                    raise CogmentError(f"Wrong type for field name [{type(field)}]")
                raw_fields.append(field)

            self._raw_params.datalog.ClearField("exclude_fields")
            self._raw_params.datalog.exclude_fields.extend(raw_fields)

    # Environment
    @property
    def environment_config(self):
        """Config sent to environment on trial start"""
        if(self._raw_params.environment.HasField("config")):
            config_instance = self._cog_settings.environment.config_type()
            config_instance.ParseFromString(self._raw_params.environment.config.content)
        else:
            config_instance = None

        return config_instance

    @environment_config.setter
    def environment_config(self, val):
        if val is None:
            self._raw_params.environment.ClearField("config")

        elif isinstance(val, self._cog_settings.environment.config_type):
            self._raw_params.environment.config.content = val.SerializeToString()

        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def environment_name(self):
        """Name of the environment"""
        return self._raw_params.environment.name

    @environment_name.setter
    def environment_name(self, val):
        if val is None:
            self._raw_params.environment.ClearField("name")
        elif type(val) is str:
            self._raw_params.environment.name = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def environment_endpoint(self):
        """Endpoint for the environment service"""
        return self._raw_params.environment.endpoint

    @environment_endpoint.setter
    def environment_endpoint(self, val):
        if val is None:
            self._raw_params.environment.ClearField("endpoint")
        elif type(val) is str:
            self._raw_params.environment.endpoint = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    @property
    def environment_implementation(self):
        """Implementation name of the environment service"""
        return self._raw_params.environment.implementation

    @environment_implementation.setter
    def environment_implementation(self, val):
        if val is None:
            self._raw_params.environment.ClearField("implementation")
        elif type(val) is str:
            self._raw_params.environment.implementation = val
        else:
            raise CogmentError(f"Wrong type [{type(val)}]")

    # Actors
    @property
    def actors(self):
        """Parameters for all actors of the trial"""
        return self._actors

    @actors.setter
    def actors(self, val):
        for param in val:
            if type(param) is not ActorParameters:
                raise CogmentError(f"Wrong type for actor parameter [{type(param)}]")

        self._actors.clear()
        self._actors.extend(val)
