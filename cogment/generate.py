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
import subprocess
import sys
import re
import typing

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

actor_classes = _cog.actor.ActorClassList({2})

trial = SimpleNamespace(config_type={3})

environment = SimpleNamespace(config_type={4})
"""


def py_path_from_proto_path(proto_file_name: str) -> str:
    return proto_file_name.split(".")[0] + "_pb2"


def py_alias_from_proto_path(proto_file_name: str) -> str:
    return proto_file_name.split(".")[0] + "_pb"


def token_as_proto_token(yaml_token: str, proto_files_content) -> str:
    token_parts = yaml_token.split(".")
    if len(token_parts) == 1:
        token_package = ""
        token_name = token_parts[0]
    elif len(token_parts) == 2:
        token_package, token_name = token_parts
    else:
        raise CogmentGenerateError(f"Invalid token format [{yaml_token}]")

    if token_package not in proto_files_content:
        raise CogmentGenerateError(f"Unknown token package [{yaml_token}]")

    for proto_file_name, proto_file_data in proto_files_content[token_package]:
        # TODO: Improve robustness of this (e.g. if name is found even in a comment, it will "work")!
        if token_name in proto_file_data:
            return f"{py_alias_from_proto_path(proto_file_name)}.{token_name}"

    raise CogmentGenerateError(f"Token [{yaml_token}] not found in any file")


def proto_import_line(proto: str) -> str:
    return (f"import {py_path_from_proto_path(proto)} as {py_alias_from_proto_path(proto)}")


def proto_lib_line(proto: str) -> str:
    return f'protolib = "{py_path_from_proto_path(proto)}"'


def actor_class_line(actor_class) -> str:
    actor_className = actor_class["name"]
    return f"_{actor_className}_class"


def generate(spec: str, output: str):
    output_directory = os.path.dirname(os.path.abspath(output))
    spec_directory = os.path.dirname(os.path.abspath(spec))

    proto_files_content: typing.Dict[str, typing.List[typing.Tuple[str, str]]] = {}

    def actor_classes_block(actor_class) -> str:
        if actor_class["observation"].get("delta") is not None:
            raise CogmentGenerateError(f"[{actor_class['name']}] defines 'observation.delta' "
                                        f"which is no longer supported.")
        if actor_class["observation"].get("delta_apply_fn") is not None:
            raise CogmentGenerateError(f"[{actor_class['name']}] defines 'observation.delta_apply_fn' "
                                        f"which is no longer supported.")

        if "config_type" in actor_class:
            config_type = token_as_proto_token(actor_class["config_type"], proto_files_content)
        else:
            config_type = "None"

        return ACTOR_CLASS_FORMAT.format(
            actor_class["name"],
            config_type,
            token_as_proto_token(actor_class["action"]["space"], proto_files_content),
            token_as_proto_token(actor_class["observation"]["space"], proto_files_content)
        )

    with open(spec, "r") as stream:
        cog_settings = yaml.safe_load(stream)

        proto_files = cog_settings["import"]["proto"]
        package_pattern = re.compile(r"^\s*package\s+(\w+)\s*;", re.MULTILINE)

        for file_name in proto_files:
            with open(os.path.join(spec_directory, file_name), "r") as file:
                file_data = file.read()
                package = re.findall(package_pattern, file_data)
                if len(package) == 1:
                    package_name = package[0]
                elif len(package) == 0:
                    package_name = ""
                else:
                    raise CogmentGenerateError(f"Only one package can be defined in proto file [{file_name}]")

                if package_name not in proto_files_content:
                    proto_files_content[package_name] = [(file_name, file_data)]
                else:
                    proto_files_content[package_name].append((file_name, file_data))

        args = [
            sys.executable,
            "-m", "grpc_tools.protoc",
            "-I", ".",
            f"--python_out={output_directory}"
        ]
        args.extend(proto_files)

        subprocess.check_call(args, cwd=spec_directory)

        if len(cog_settings.get("import", {}).get("python", [])) > 0:
            raise CogmentGenerateError("Python imports in configuration file are not supported in Cogment 2.0 "
                                        "spec file")

        if "trial" in cog_settings and "config_type" in cog_settings["trial"]:
            trial_config = token_as_proto_token(cog_settings["trial"]["config_type"], proto_files_content)
        else:
            trial_config = "None"

        if "environment" in cog_settings and "config_type" in cog_settings["environment"]:
            env_config = token_as_proto_token(cog_settings["environment"]["config_type"], proto_files_content)
        else:
            env_config = "None"

        line_break = "\n"  # f strings can't have backslashes in them
        comma_line_break_tab = ",\n\t"  # f strings can't have backslashes in them

        proto_import_lines = []
        for proto_import_file in proto_files:
            proto_import_lines.append(proto_import_line(proto_import_file))

        actor_class_lines = []
        actor_class_blocks = []
        actor_classes = cog_settings.get("actor_classes", [])
        for actor_class in actor_classes:
            actor_class_lines.append(actor_class_line(actor_class))
            actor_class_blocks.append(actor_classes_block(actor_class))

        cog_settings_string = COG_SETTINGS_FORMAT.format(
            line_break.join(proto_import_lines),
            line_break.join(actor_class_blocks),
            comma_line_break_tab.join(actor_class_lines),
            trial_config,
            env_config)

        with open(output, "w") as text_file:
            text_file.write(cog_settings_string)


@click.command()
@click.option("--spec", default="cogment.yaml", help="Cogment spec file")
@click.option("--output", default="cog_settings.py", help="Output python file")
def main(spec: str, output: str):
    generate(spec, output)


if __name__ == "__main__":
    main()
