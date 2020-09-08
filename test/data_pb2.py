# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: test/data.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='test/data.proto',
  package='mytest',
  syntax='proto3',
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n\x0ftest/data.proto\x12\x06mytest\"\x1c\n\x0bObservation\x12\r\n\x05value\x18\x01 \x01(\x05\"\x17\n\x06\x41\x63tion\x12\r\n\x05value\x18\x01 \x01(\x05\"4\n\x0bTrialConfig\x12%\n\nenv_config\x18\x01 \x01(\x0b\x32\x11.mytest.EnvConfig\"1\n\tEnvConfig\x12\x12\n\nnum_agents\x18\x01 \x01(\x05\x12\x10\n\x08str_test\x18\x02 \x01(\t\"\x1b\n\x0bMessageTest\x12\x0c\n\x04name\x18\x01 \x01(\tb\x06proto3'
)




_OBSERVATION = _descriptor.Descriptor(
  name='Observation',
  full_name='mytest.Observation',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='value', full_name='mytest.Observation.value', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=27,
  serialized_end=55,
)


_ACTION = _descriptor.Descriptor(
  name='Action',
  full_name='mytest.Action',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='value', full_name='mytest.Action.value', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=57,
  serialized_end=80,
)


_TRIALCONFIG = _descriptor.Descriptor(
  name='TrialConfig',
  full_name='mytest.TrialConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='env_config', full_name='mytest.TrialConfig.env_config', index=0,
      number=1, type=11, cpp_type=10, label=1,
      has_default_value=False, default_value=None,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=82,
  serialized_end=134,
)


_ENVCONFIG = _descriptor.Descriptor(
  name='EnvConfig',
  full_name='mytest.EnvConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='num_agents', full_name='mytest.EnvConfig.num_agents', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='str_test', full_name='mytest.EnvConfig.str_test', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=136,
  serialized_end=185,
)


_MESSAGETEST = _descriptor.Descriptor(
  name='MessageTest',
  full_name='mytest.MessageTest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='name', full_name='mytest.MessageTest.name', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=187,
  serialized_end=214,
)

_TRIALCONFIG.fields_by_name['env_config'].message_type = _ENVCONFIG
DESCRIPTOR.message_types_by_name['Observation'] = _OBSERVATION
DESCRIPTOR.message_types_by_name['Action'] = _ACTION
DESCRIPTOR.message_types_by_name['TrialConfig'] = _TRIALCONFIG
DESCRIPTOR.message_types_by_name['EnvConfig'] = _ENVCONFIG
DESCRIPTOR.message_types_by_name['MessageTest'] = _MESSAGETEST
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

Observation = _reflection.GeneratedProtocolMessageType('Observation', (_message.Message,), {
  'DESCRIPTOR' : _OBSERVATION,
  '__module__' : 'test.data_pb2'
  # @@protoc_insertion_point(class_scope:mytest.Observation)
  })
_sym_db.RegisterMessage(Observation)

Action = _reflection.GeneratedProtocolMessageType('Action', (_message.Message,), {
  'DESCRIPTOR' : _ACTION,
  '__module__' : 'test.data_pb2'
  # @@protoc_insertion_point(class_scope:mytest.Action)
  })
_sym_db.RegisterMessage(Action)

TrialConfig = _reflection.GeneratedProtocolMessageType('TrialConfig', (_message.Message,), {
  'DESCRIPTOR' : _TRIALCONFIG,
  '__module__' : 'test.data_pb2'
  # @@protoc_insertion_point(class_scope:mytest.TrialConfig)
  })
_sym_db.RegisterMessage(TrialConfig)

EnvConfig = _reflection.GeneratedProtocolMessageType('EnvConfig', (_message.Message,), {
  'DESCRIPTOR' : _ENVCONFIG,
  '__module__' : 'test.data_pb2'
  # @@protoc_insertion_point(class_scope:mytest.EnvConfig)
  })
_sym_db.RegisterMessage(EnvConfig)

MessageTest = _reflection.GeneratedProtocolMessageType('MessageTest', (_message.Message,), {
  'DESCRIPTOR' : _MESSAGETEST,
  '__module__' : 'test.data_pb2'
  # @@protoc_insertion_point(class_scope:mytest.MessageTest)
  })
_sym_db.RegisterMessage(MessageTest)


# @@protoc_insertion_point(module_scope)
