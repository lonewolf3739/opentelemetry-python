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

"""

OpenTelemetry Jaeger Protobuf Exporter
--------------------------------------

The **OpenTelemetry Jaeger Protobuf Exporter** allows to export `OpenTelemetry`_ traces to `Jaeger`_.
This exporter always sends traces to the configured agent using Protobuf via gRPC.

Usage
-----

.. code:: python

    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)

    # create a JaegerExporter
    jaeger_exporter = JaegerExporter(
        # optional: configure collector
        # collector_endpoint='localhost:14250',
        # insecure=True, # optional
        # credentials=xxx # optional channel creds
        # max_tag_value_length=None # optional
    )

    # Create a BatchSpanProcessor and add the exporter to it
    span_processor = BatchSpanProcessor(jaeger_exporter)

    # add to the tracer
    trace.get_tracer_provider().add_span_processor(span_processor)

    with tracer.start_as_current_span('foo'):
        print('Hello world!')

You can configure the exporter with the following environment variables:

- :envvar:`OTEL_EXPORTER_JAEGER_ENDPOINT`
- :envvar:`OTEL_EXPORTER_JAEGER_CERTIFICATE`

API
---
.. _Jaeger: https://www.jaegertracing.io/
.. _OpenTelemetry: https://github.com/open-telemetry/opentelemetry-python/
"""
# pylint: disable=protected-access

import logging
from os import environ
from typing import Optional, Sequence

from grpc import ChannelCredentials, insecure_channel, secure_channel

from opentelemetry import trace
from opentelemetry.exporter.jaeger.proto.grpc import util
from opentelemetry.exporter.jaeger.proto.grpc.gen import model_pb2
from opentelemetry.exporter.jaeger.proto.grpc.gen.collector_pb2 import (
    PostSpansRequest,
)
from opentelemetry.exporter.jaeger.proto.grpc.gen.collector_pb2_grpc import (
    CollectorServiceStub,
)
from opentelemetry.exporter.jaeger.proto.grpc.translate import _ProtobufEncoder
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_JAEGER_ENDPOINT,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

DEFAULT_GRPC_COLLECTOR_ENDPOINT = "localhost:14250"

logger = logging.getLogger(__name__)


class JaegerExporter(SpanExporter):
    """Jaeger span exporter for OpenTelemetry.

    Args:
        collector_endpoint: The endpoint of the Jaeger collector that uses
            Protobuf via gRPC. The default endpoint is "localhost:14250".
        insecure: True if collector has no encryption or authentication
        credentials: Credentials for server authentication.
        max_tag_value_length: Max length string attribute values can have. Set to None to disable.
    """

    def __init__(
        self,
        collector_endpoint: Optional[str] = None,
        insecure: Optional[bool] = None,
        credentials: Optional[ChannelCredentials] = None,
        max_tag_value_length: Optional[int] = None,
    ):
        self._max_tag_value_length = max_tag_value_length
        self.collector_endpoint = collector_endpoint or environ.get(
            OTEL_EXPORTER_JAEGER_ENDPOINT, DEFAULT_GRPC_COLLECTOR_ENDPOINT
        )
        self.credentials = util._get_credentials(credentials)
        if insecure:
            self._stub = CollectorServiceStub(
                insecure_channel(self.collector_endpoint)
            )
        else:
            self._stub = CollectorServiceStub(
                secure_channel(self.collector_endpoint, self.credentials)
            )
        self._encoder = _ProtobufEncoder(self._max_tag_value_length)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if spans:
            batch = self._encoder.encode(spans)
            request = PostSpansRequest(batch=batch)
            self._stub.PostSpans(request)

        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass
