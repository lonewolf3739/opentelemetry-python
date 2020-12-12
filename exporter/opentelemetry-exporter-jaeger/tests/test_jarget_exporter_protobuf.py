# Copyright 2018, OpenCensus Authors
# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

from google.protobuf.timestamp_pb2 import Timestamp

# pylint:disable=no-name-in-module
# pylint:disable=import-error
import opentelemetry.exporter.jaeger as jaeger_exporter
import opentelemetry.exporter.jaeger.gen.model_pb2 as model_pb2
import opentelemetry.exporter.jaeger.translate as translate
from opentelemetry import trace as trace_api
from opentelemetry.configuration import Configuration
from opentelemetry.sdk import trace
from opentelemetry.sdk.trace import Resource
from opentelemetry.sdk.util.instrumentation import InstrumentationInfo
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode

# pylint:disable=protected-access
class TestJaegerSpanExporter(unittest.TestCase):
    def setUp(self):
        # create and save span to be used in tests
        context = trace_api.SpanContext(
            trace_id=0x000000000000000000000000DEADBEEF,
            span_id=0x00000000DEADBEF0,
            is_remote=False,
        )

        self._test_span = trace._Span("test_span", context=context)
        self._test_span.start()
        self._test_span.end()
        # pylint: disable=protected-access
        Configuration._reset()

    def tearDown(self):
        # pylint: disable=protected-access
        Configuration._reset()

    def test_nsec_to_usec_round(self):
        # pylint: disable=protected-access
        nsec_to_usec_round = jaeger_exporter.translate._nsec_to_usec_round

        self.assertEqual(nsec_to_usec_round(5000), 5)
        self.assertEqual(nsec_to_usec_round(5499), 5)
        self.assertEqual(nsec_to_usec_round(5500), 6)

    def test_all_otlp_span_kinds_are_mapped(self):
        for kind in SpanKind:
            self.assertIn(
                kind, jaeger_exporter.translate.OTLP_JAEGER_SPAN_KIND
            )

    # pylint: disable=too-many-locals,protected-access
    def test_translate_to_jaeger(self):
        # pylint: disable=invalid-name
        self.maxDiff = None

        span_names = ("test1", "test2", "test3")
        trace_id = 0x6E0C63257DE34C926F9EFCD03927272E
        span_id = 0x34BF92DEEFC58C92
        parent_id = 0x1111111111111111
        other_id = 0x2222222222222222

        base_time = int(0.683647322 * (10 ** 9))  # in ns
        start_times = (
            base_time,
            base_time + 150 * 10 ** 6,
            base_time + 300 * 10 ** 6,
        )
        durations = (50 * 10 ** 6, 100 * 10 ** 6, 200 * 10 ** 6)
        end_times = (
            start_times[0] + durations[0],
            start_times[1] + durations[1],
            start_times[2] + durations[2],
        )

        span_context = trace_api.SpanContext(
            trace_id, span_id, is_remote=False
        )
        parent_span_context = trace_api.SpanContext(
            trace_id, parent_id, is_remote=False
        )
        other_context = trace_api.SpanContext(
            trace_id, other_id, is_remote=False
        )

        event_attributes = {
            "annotation_bool": True,
            "annotation_string": "annotation_test",
            "key_float": 0.3,
        }

        event_timestamp = base_time + 50 * 10 ** 6
        event_timestamp_proto = translate.protobuf._proto_timestamp_from_epoch_nanos(
            event_timestamp
        )

        event = trace.Event(
            name="event0",
            timestamp=event_timestamp,
            attributes=event_attributes,
        )

        link_attributes = {"key_bool": True}

        link = trace_api.Link(
            context=other_context, attributes=link_attributes
        )

        default_tags = [
            model_pb2.KeyValue(
                key="status.code",
                v_type=model_pb2.ValueType.INT64,
                v_int64=StatusCode.UNSET.value,
            ),
            model_pb2.KeyValue(
                key="status.message",
                v_type=model_pb2.ValueType.STRING,
                v_str=None,
            ),
            model_pb2.KeyValue(
                key="span.kind",
                v_type=model_pb2.ValueType.STRING,
                v_str="internal",
            ),
        ]

        otel_spans = [
            trace._Span(
                name=span_names[0],
                context=span_context,
                parent=parent_span_context,
                events=(event,),
                links=(link,),
                kind=trace_api.SpanKind.CLIENT,
            ),
            trace._Span(
                name=span_names[1], context=parent_span_context, parent=None
            ),
            trace._Span(
                name=span_names[2], context=other_context, parent=None
            ),
        ]

        otel_spans[0].start(start_time=start_times[0])
        # added here to preserve order
        otel_spans[0].set_attribute("key_bool", False)
        otel_spans[0].set_attribute("key_string", "hello_world")
        otel_spans[0].set_attribute("key_float", 111.22)
        otel_spans[0].set_attribute("key_tuple", ("tuple_element",))
        otel_spans[0].resource = Resource(
            attributes={"key_resource": "some_resource"}
        )
        otel_spans[0].set_status(
            Status(StatusCode.ERROR, "Example description")
        )
        otel_spans[0].end(end_time=end_times[0])

        otel_spans[1].start(start_time=start_times[1])
        otel_spans[1].resource = Resource({})
        otel_spans[1].end(end_time=end_times[1])

        otel_spans[2].start(start_time=start_times[2])
        otel_spans[2].resource = Resource({})
        otel_spans[2].set_status(Status(StatusCode.OK, "Example description"))
        otel_spans[2].end(end_time=end_times[2])
        otel_spans[2].instrumentation_info = InstrumentationInfo(
            name="name", version="version"
        )

        # pylint: disable=protected-access
        spans = translate.protobuf._to_jaeger(otel_spans, "svc")

        span1_start_time = translate.protobuf._proto_timestamp_from_epoch_nanos(
            start_times[0]
        )
        span2_start_time = translate.protobuf._proto_timestamp_from_epoch_nanos(
            start_times[1]
        )
        span3_start_time = translate.protobuf._proto_timestamp_from_epoch_nanos(
            start_times[2]
        )

        span1_end_time = translate.protobuf._proto_timestamp_from_epoch_nanos(
            end_times[0]
        )
        span2_end_time = translate.protobuf._proto_timestamp_from_epoch_nanos(
            end_times[1]
        )
        span3_end_time = translate.protobuf._proto_timestamp_from_epoch_nanos(
            end_times[2]
        )

        span1_duration = translate.protobuf._duration_from_two_time_stamps(
            span1_start_time, span1_end_time
        )
        span2_duration = translate.protobuf._duration_from_two_time_stamps(
            span2_start_time, span2_end_time
        )
        span3_duration = translate.protobuf._duration_from_two_time_stamps(
            span3_start_time, span3_end_time
        )

        expected_spans = [
            model_pb2.Span(
                operation_name=span_names[0],
                trace_id=translate.protobuf._trace_id_to_bytes(trace_id),
                span_id=translate.protobuf._span_id_to_bytes(span_id),
                start_time=span1_start_time,
                duration=span1_duration,
                flags=0,
                tags=[
                    model_pb2.KeyValue(
                        key="key_bool",
                        v_type=model_pb2.ValueType.BOOL,
                        v_bool=False,
                    ),
                    model_pb2.KeyValue(
                        key="key_string",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="hello_world",
                    ),
                    model_pb2.KeyValue(
                        key="key_float",
                        v_type=model_pb2.ValueType.FLOAT64,
                        v_float64=111.22,
                    ),
                    model_pb2.KeyValue(
                        key="key_tuple",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="('tuple_element',)",
                    ),
                    model_pb2.KeyValue(
                        key="key_resource",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="some_resource",
                    ),
                    model_pb2.KeyValue(
                        key="status.code",
                        v_type=model_pb2.ValueType.INT64,
                        v_int64=StatusCode.ERROR.value,
                    ),
                    model_pb2.KeyValue(
                        key="status.message",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="Example description",
                    ),
                    model_pb2.KeyValue(
                        key="span.kind",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="client",
                    ),
                    model_pb2.KeyValue(
                        key="error",
                        v_type=model_pb2.ValueType.BOOL,
                        v_bool=True,
                    ),
                ],
                references=[
                    model_pb2.SpanRef(
                        ref_type=model_pb2.SpanRefType.FOLLOWS_FROM,
                        trace_id=translate.protobuf._trace_id_to_bytes(
                            trace_id
                        ),
                        span_id=translate.protobuf._span_id_to_bytes(other_id),
                    )
                ],
                logs=[
                    model_pb2.Log(
                        timestamp=event_timestamp_proto,
                        fields=[
                            model_pb2.KeyValue(
                                key="annotation_bool",
                                v_type=model_pb2.ValueType.BOOL,
                                v_bool=True,
                            ),
                            model_pb2.KeyValue(
                                key="annotation_string",
                                v_type=model_pb2.ValueType.STRING,
                                v_str="annotation_test",
                            ),
                            model_pb2.KeyValue(
                                key="key_float",
                                v_type=model_pb2.ValueType.FLOAT64,
                                v_float64=0.3,
                            ),
                            model_pb2.KeyValue(
                                key="message",
                                v_type=model_pb2.ValueType.STRING,
                                v_str="event0",
                            ),
                        ],
                    )
                ],
                process=model_pb2.Process(
                    service_name="svc",
                    tags=[
                        model_pb2.KeyValue(
                            key="key_resource",
                            v_str="some_resource",
                            v_type=model_pb2.ValueType.STRING,
                        )
                    ],
                ),
            ),
            model_pb2.Span(
                operation_name=span_names[1],
                trace_id=translate.protobuf._trace_id_to_bytes(trace_id),
                span_id=translate.protobuf._span_id_to_bytes(parent_id),
                start_time=span2_start_time,
                duration=span2_duration,
                flags=0,
                tags=default_tags,
                process=model_pb2.Process(service_name="svc",),
            ),
            model_pb2.Span(
                operation_name=span_names[2],
                trace_id=translate.protobuf._trace_id_to_bytes(trace_id),
                span_id=translate.protobuf._span_id_to_bytes(other_id),
                start_time=span3_start_time,
                duration=span3_duration,
                flags=0,
                tags=[
                    model_pb2.KeyValue(
                        key="status.code",
                        v_type=model_pb2.ValueType.INT64,
                        v_int64=StatusCode.OK.value,
                    ),
                    model_pb2.KeyValue(
                        key="status.message",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="Example description",
                    ),
                    model_pb2.KeyValue(
                        key="span.kind",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="internal",
                    ),
                    model_pb2.KeyValue(
                        key="otel.instrumentation_library.name",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="name",
                    ),
                    model_pb2.KeyValue(
                        key="otel.instrumentation_library.version",
                        v_type=model_pb2.ValueType.STRING,
                        v_str="version",
                    ),
                ],
                process=model_pb2.Process(service_name="svc",),
            ),
        ]

        # events are complicated to compare because order of fields
        # (attributes) in otel is not important but in jeager it is
        self.assertCountEqual(
            spans[0].logs[0].fields, expected_spans[0].logs[0].fields
        )

        self.assertEqual(spans, expected_spans)
