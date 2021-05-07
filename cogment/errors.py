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

class Error(Exception):

    def __init__(self, msg):
        super().__init__(msg)


class InvalidRequestError(Error):

    def __init__(self, message, request):
        self.request = request
        super().__init__(message)


class InvalidParamsError(Error):

    def __init__(self, msg):
        super().__init__(msg)
