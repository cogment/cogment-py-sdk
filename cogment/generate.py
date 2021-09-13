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

import os
import glob
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    raise Exception('''
        The `cogment.generate` module requires extra dependencies,
        please install by running `pip install cogment[generate]`
    ''')


def py_path_from_proto_path(proto: str) -> str:
    return proto.split(".")[0] + "_pb2"


def py_alias_from_proto_path(proto: str) -> str:
    return proto.split(".")[0] + "_pb"


def token_as_proto_token(yaml_token: str, proto_file_content) -> str:
    token = yaml_token.split(".")[1]

    for file in proto_file_content:
        if token in proto_file_content[file]:
            return f"{py_alias_from_proto_path(file)}.{token}"

    raise Exception(f"TOKEN {token} NOT FOUND IN ANY FILE")


def proto_import_line(proto: str) -> str:
    return (
        f"import {py_path_from_proto_path(proto)} as {py_alias_from_proto_path(proto)}"
    )


def python_import_line(py_module: str) -> str:
    return f"import {py_module}"


def proto_lib_line(proto: str) -> str:
    return f'protolib = "{py_path_from_proto_path(proto)}"'


def actor_class_line(actor_class) -> str:
    actor_className = actor_class["name"]
    return f"_{actor_className}_class"


def main():

    # Closure with proto_file_content in it
    def actor_classes_block(actor_class) -> str:
        return f"""
_{actor_class['name']}_class = _cog.actor.ActorClass(
    name="{actor_class['name']}",
    config_type={token_as_proto_token(actor_class['config_type'], proto_file_content)
        if 'config_type' in actor_class else 'None'},
    action_space={token_as_proto_token(actor_class['action']['space'], proto_file_content)},
    observation_space={token_as_proto_token(actor_class['observation']['space'], proto_file_content)},
    observation_delta={token_as_proto_token(actor_class['observation']['delta'], proto_file_content)
        if 'delta' in actor_class['observation']
        else token_as_proto_token(actor_class['observation']['space'], proto_file_content)},
    observation_delta_apply_fn=_cog.delta_encoding._apply_delta_replace,
)
        """

    with open("cogment.yaml", "r") as stream:
        cog_settings = yaml.safe_load(stream)

        proto_files = cog_settings["import"]["proto"]
        proto_file_content = {}

        for file in proto_files:
            with open(file, "r") as file_data:
                proto_file_content[file] = file_data.read()

        os.system(
            "python -m grpc_tools.protoc -I . --python_out=. " + " ".join(proto_files)
        )

        line_break = "\n"  # f strings can't have backslashes in them
        comma_line_break_tab = ",\n\t"  # f strings can't have backslashes in them

        cog_settings_string = f"""
import cogment as _cog
from types import SimpleNamespace
from typing import List

{line_break.join(map(proto_import_line, cog_settings.get('import', {}).get('proto', [])))}
{line_break.join(map(python_import_line, cog_settings.get('import', {}).get('python', [])))}
{line_break.join(map(proto_lib_line, cog_settings.get('import', {}).get('proto', [])))}
{line_break.join(map(actor_classes_block, cog_settings.get('actor_classes', [])))}

actor_classes = _cog.actor.ActorClassList(
    {comma_line_break_tab.join(map(actor_class_line, cog_settings.get('actor_classes', [])))}
)

trial = SimpleNamespace(config_type={token_as_proto_token(cog_settings['trial']['config_type'], proto_file_content)
    if 'trial' in cog_settings and 'config_type' in cog_settings['trial']
    else 'None'})

# Environment
environment = SimpleNamespace(config_type={
    token_as_proto_token(cog_settings['environment']['config_type'], proto_file_content)
    if 'environment' in cog_settings and 'config_type' in cog_settings['environment']
    else 'None'})
        """
        with open("cog_settings.py", "w") as text_file:
            text_file.write(cog_settings_string)


if __name__ == "__main__":
    main()
