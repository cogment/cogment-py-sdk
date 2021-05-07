# Copyright 2021 Artificial Intelligence Redefined <dev+cogment@ai-r.com>
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

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This is the main import module for the cogment (https://gitlab.com/cogment/cogment) AI
framework python SDK by AI Redefined Inc.
"""

from cogment.version import __version__

from cogment.context import Context, Endpoint, ServedEndpoint
from cogment.session import EventType
from cogment.control import TrialState

# Necessary because of cogment CLI "cog_settings.py" generated code
from cogment.actor import ActorClass, ActorClassList
import cogment.delta_encoding
