# Copyright 2023 AI Redefined Inc. <dev+cogment@ai-r.com>
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

import helpers.download_cogment
from cogment.errors import CogmentError


import pytest

import asyncio
import unittest
import urllib.request
import logging
import subprocess

logger = logging.getLogger("cogment.unit-tests")


def test_get_latest_version(unittest_case):
    unittest_case.assertRegex(helpers.download_cogment.get_latest_release_version(), r"v[0-9]+\.[0-9]+\.[0-9]+")


def test_get_os(unittest_case):
    unittest_case.assertIn(helpers.download_cogment.get_current_os(), helpers.download_cogment.Os)


def test_get_arch(unittest_case):
    unittest_case.assertIn(helpers.download_cogment.get_current_arch(), helpers.download_cogment.Arch)


def test_download_latest_cogment(unittest_case):
    cogment_path = helpers.download_cogment.download_cogment()

    # Can it run?
    subprocess.run([cogment_path, "version"], capture_output=True)


def test_download_cogment_2_2(unittest_case):
    if helpers.download_cogment.get_current_arch() == helpers.download_cogment.Arch.ARM64:
        with unittest_case.assertRaises(CogmentError):
            helpers.download_cogment.download_cogment(desired_version="v2.2.0")
        return
    cogment_path = helpers.download_cogment.download_cogment(desired_version="v2.2.0")

    completed_process = subprocess.run([cogment_path, "version"], capture_output=True)
    unittest_case.assertTrue(completed_process.stdout.decode('utf-8').strip().startswith("2.2.0"))
