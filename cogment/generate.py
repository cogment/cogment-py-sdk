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

from cogment.errors import CogmentGenerateError

try:
    import click
    import yaml
except ModuleNotFoundError:
    raise CogmentGenerateError("The `cogment.generate` module requires extra dependencies, "
                       "please install by running `pip install cogment[generate]`")

ACTOR_CLASS_FORMAT = """
_{0}_class = _cog.actor.ActorClass(
            name="{0}",
            config_type={1},
            action_space={2},
            observation_space={3},
            )
"""

COG_SETTINGS_FORMAT = """
import cogment as _cog
from types import SimpleNamespace

{0}
{1}
{2}

actor_classes = _cog.actor.ActorClassList({3})

trial = SimpleNamespace(config_type={4})

environment = SimpleNamespace(config_type={5})
"""


def py_path_from_proto_path(proto: str) -> str:
    return proto.split(".")[0] + "_pb2"


def py_alias_from_proto_path(proto: str) -> str:
    return proto.split(".")[0] + "_pb"


def token_as_proto_token(yaml_token: str, proto_file_content) -> str:
    token = yaml_token.split(".")[1]

    for file in proto_file_content:
        if token in proto_file_content[file]:
            return f"{py_alias_from_proto_path(file)}.{token}"

    raise CogmentGenerateError(f"Token [{token}] not found in any file")


def proto_import_line(proto: str) -> str:
    return (f"import {py_path_from_proto_path(proto)} as {py_alias_from_proto_path(proto)}")


def proto_lib_line(proto: str) -> str:
    return f'protolib = "{py_path_from_proto_path(proto)}"'


def actor_class_line(actor_class) -> str:
    actor_className = actor_class["name"]
    return f"_{actor_className}_class"


@click.command()
@click.option("--spec", default="cogment.yaml", help="Cogment spec file")
@click.option("--output", default="cog_settings.py", help="Output python file")
def main(spec: str, output: str):

    output_directory = os.path.dirname(os.path.abspath(output))

    # Closure with proto_file_content in it
    def actor_classes_block(actor_class) -> str:
        if actor_class["observation"].get("delta") is not None:
            raise CogmentGenerateError(f"[{actor_class['name']}] defines 'observation.delta' "
                                        f"which is no longer supported.")
        if actor_class["observation"].get("delta_apply_fn") is not None:
            raise CogmentGenerateError(f"[{actor_class['name']}] defines 'observation.delta_apply_fn' "
                                        f"which is no longer supported.")

        if "config_type" in actor_class:
            config_type = token_as_proto_token(actor_class["config_type"], proto_file_content)
        else:
            config_type = "None"

        return ACTOR_CLASS_FORMAT.format(
            actor_class["name"],
            config_type,
            token_as_proto_token(actor_class["action"]["space"], proto_file_content),
            token_as_proto_token(actor_class["observation"]["space"], proto_file_content)
        )

    with open(spec, "r") as stream:
        cog_settings = yaml.safe_load(stream)

        proto_files = cog_settings["import"]["proto"]
        proto_file_content = {}

        for file in proto_files:
            with open(file, "r") as file_data:
                proto_file_content[file] = file_data.read()

        os.system(f"python -m grpc_tools.protoc -I . --python_out={output_directory} {' '.join(proto_files)}")

        if len(cog_settings.get("import", {}).get("python", [])) > 0:
            raise CogmentGenerateError("Python imports in configuration file are not supported in Cogment 2.0 "
                                        "spec file")

        if "trial" in cog_settings and "config_type" in cog_settings["trial"]:
            trial_config = token_as_proto_token(cog_settings["trial"]["config_type"], proto_file_content)
        else:
            trial_config = "None"

        if "environment" in cog_settings and "config_type" in cog_settings["environment"]:
            env_config = token_as_proto_token(cog_settings["environment"]["config_type"], proto_file_content)
        else:
            env_config = "None"

        line_break = "\n"  # f strings can't have backslashes in them
        comma_line_break_tab = ",\n\t"  # f strings can't have backslashes in them

        proto_import_lines = []
        proto_lib_lines = []
        proto_imports = cog_settings.get("import", {}).get("proto", [])
        for proto_import in proto_imports:
            proto_import_lines.append(proto_import_line(proto_import))
            proto_lib_lines.append(proto_lib_line(proto_import))

        actor_class_lines = []
        actor_class_blocks = []
        actor_classes = cog_settings.get("actor_classes", [])
        for actor_class in actor_classes:
            actor_class_lines.append(actor_class_line(actor_class))
            actor_class_blocks.append(actor_classes_block(actor_class))

        cog_settings_string = COG_SETTINGS_FORMAT.format(
            line_break.join(proto_import_lines),
            line_break.join(proto_lib_lines),
            line_break.join(actor_class_blocks),
            comma_line_break_tab.join(actor_class_lines),
            trial_config,
            env_config)

        with open(output, "w") as text_file:
            text_file.write(cog_settings_string)


if __name__ == "__main__":
    main()
