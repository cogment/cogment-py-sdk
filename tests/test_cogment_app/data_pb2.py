# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: data.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='data.proto',
  package='test_cogment_app',
  syntax='proto3',
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n\ndata.proto\x12\x10test_cogment_app\"\x0b\n\tEnvConfig\">\n\x0bTrialConfig\x12/\n\nenv_config\x18\x01 \x01(\x0b\x32\x1b.test_cogment_app.EnvConfig\"%\n\x0bObservation\x12\x16\n\x0eobserved_value\x18\x01 \x01(\x05\"\x1e\n\x06\x41\x63tion\x12\x14\n\x0c\x61\x63tion_value\x18\x01 \x01(\x05\"5\n\x11MyMessageUserData\x12\x10\n\x08\x61_string\x18\x01 \x01(\t\x12\x0e\n\x06\x61n_int\x18\x03 \x01(\x05\"5\n\x12MyFeedbackUserData\x12\x0e\n\x06\x61_bool\x18\x01 \x01(\x08\x12\x0f\n\x07\x61_float\x18\x02 \x01(\x02\x62\x06proto3'
)




_ENVCONFIG = _descriptor.Descriptor(
  name='EnvConfig',
  full_name='test_cogment_app.EnvConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
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
  serialized_start=32,
  serialized_end=43,
)


_TRIALCONFIG = _descriptor.Descriptor(
  name='TrialConfig',
  full_name='test_cogment_app.TrialConfig',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='env_config', full_name='test_cogment_app.TrialConfig.env_config', index=0,
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
  serialized_start=45,
  serialized_end=107,
)


_OBSERVATION = _descriptor.Descriptor(
  name='Observation',
  full_name='test_cogment_app.Observation',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='observed_value', full_name='test_cogment_app.Observation.observed_value', index=0,
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
  serialized_start=109,
  serialized_end=146,
)


_ACTION = _descriptor.Descriptor(
  name='Action',
  full_name='test_cogment_app.Action',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='action_value', full_name='test_cogment_app.Action.action_value', index=0,
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
  serialized_start=148,
  serialized_end=178,
)


_MYMESSAGEUSERDATA = _descriptor.Descriptor(
  name='MyMessageUserData',
  full_name='test_cogment_app.MyMessageUserData',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='a_string', full_name='test_cogment_app.MyMessageUserData.a_string', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='an_int', full_name='test_cogment_app.MyMessageUserData.an_int', index=1,
      number=3, type=5, cpp_type=1, label=1,
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
  serialized_start=180,
  serialized_end=233,
)


_MYFEEDBACKUSERDATA = _descriptor.Descriptor(
  name='MyFeedbackUserData',
  full_name='test_cogment_app.MyFeedbackUserData',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='a_bool', full_name='test_cogment_app.MyFeedbackUserData.a_bool', index=0,
      number=1, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='a_float', full_name='test_cogment_app.MyFeedbackUserData.a_float', index=1,
      number=2, type=2, cpp_type=6, label=1,
      has_default_value=False, default_value=float(0),
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
  serialized_start=235,
  serialized_end=288,
)

_TRIALCONFIG.fields_by_name['env_config'].message_type = _ENVCONFIG
DESCRIPTOR.message_types_by_name['EnvConfig'] = _ENVCONFIG
DESCRIPTOR.message_types_by_name['TrialConfig'] = _TRIALCONFIG
DESCRIPTOR.message_types_by_name['Observation'] = _OBSERVATION
DESCRIPTOR.message_types_by_name['Action'] = _ACTION
DESCRIPTOR.message_types_by_name['MyMessageUserData'] = _MYMESSAGEUSERDATA
DESCRIPTOR.message_types_by_name['MyFeedbackUserData'] = _MYFEEDBACKUSERDATA
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

EnvConfig = _reflection.GeneratedProtocolMessageType('EnvConfig', (_message.Message,), {
  'DESCRIPTOR' : _ENVCONFIG,
  '__module__' : 'data_pb2'
  # @@protoc_insertion_point(class_scope:test_cogment_app.EnvConfig)
  })
_sym_db.RegisterMessage(EnvConfig)

TrialConfig = _reflection.GeneratedProtocolMessageType('TrialConfig', (_message.Message,), {
  'DESCRIPTOR' : _TRIALCONFIG,
  '__module__' : 'data_pb2'
  # @@protoc_insertion_point(class_scope:test_cogment_app.TrialConfig)
  })
_sym_db.RegisterMessage(TrialConfig)

Observation = _reflection.GeneratedProtocolMessageType('Observation', (_message.Message,), {
  'DESCRIPTOR' : _OBSERVATION,
  '__module__' : 'data_pb2'
  # @@protoc_insertion_point(class_scope:test_cogment_app.Observation)
  })
_sym_db.RegisterMessage(Observation)

Action = _reflection.GeneratedProtocolMessageType('Action', (_message.Message,), {
  'DESCRIPTOR' : _ACTION,
  '__module__' : 'data_pb2'
  # @@protoc_insertion_point(class_scope:test_cogment_app.Action)
  })
_sym_db.RegisterMessage(Action)

MyMessageUserData = _reflection.GeneratedProtocolMessageType('MyMessageUserData', (_message.Message,), {
  'DESCRIPTOR' : _MYMESSAGEUSERDATA,
  '__module__' : 'data_pb2'
  # @@protoc_insertion_point(class_scope:test_cogment_app.MyMessageUserData)
  })
_sym_db.RegisterMessage(MyMessageUserData)

MyFeedbackUserData = _reflection.GeneratedProtocolMessageType('MyFeedbackUserData', (_message.Message,), {
  'DESCRIPTOR' : _MYFEEDBACKUSERDATA,
  '__module__' : 'data_pb2'
  # @@protoc_insertion_point(class_scope:test_cogment_app.MyFeedbackUserData)
  })
_sym_db.RegisterMessage(MyFeedbackUserData)


# @@protoc_insertion_point(module_scope)
