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

"""OTLP Logs Exporter"""

import logging
from typing import Optional, Sequence

from grpc import ChannelCredentials, Compression


from opentelemetry.exporter.otlp.proto.grpc.exporter import (
    OTLPExporterMixin,
    _translate_key_values,
    get_resource_data,
)

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import (
    LogsServiceStub,
)
from opentelemetry.proto.common.v1.common_pb2 import InstrumentationLibrary
from opentelemetry.proto.logs.v1.logs_pb2 import (
    InstrumentationLibraryLogs,
    ResourceLogs,
    SeverityNumber,
)
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord as PB2LogRecord
from opentelemetry.sdk.logs import OTELLogRecord, LogData
from opentelemetry.sdk.logs.export import LogExporter, LogExportResult

_DEFAULT_ENDPOINT = "localhost:4317"
_DEFAULT_INSECURE = False
_DEFAULT_TIMEOUT = 10  # in seconds


_logger = logging.getLogger(__name__)


class OTLPLogExporter(
    LogExporter,
    OTLPExporterMixin[
        OTELLogRecord, ExportLogsServiceRequest, LogExportResult
    ],
):

    _result = LogExportResult
    _stub = LogsServiceStub

    def __init__(
        self,
        endpoint: Optional[str] = None,
        insecure: Optional[bool] = None,
        credentials: Optional[ChannelCredentials] = None,
        headers: Optional[Sequence] = None,
        timeout: Optional[int] = None,
        compression: Optional[Compression] = None,
    ):
        endpoint = endpoint or _DEFAULT_ENDPOINT
        insecure = insecure or _DEFAULT_INSECURE
        timeout = timeout or _DEFAULT_TIMEOUT

        super().__init__(
            **{
                "endpoint": endpoint,
                "insecure": insecure,
                "credentials": credentials,
                "headers": headers,
                "timeout": timeout,
                "compression": compression,
            }
        )

    def _translate_name(self, log_record: OTELLogRecord) -> None:
        if log_record.name is not None:
            self._collector_log_kwargs["name"] = log_record.name

    def _translate_time(self, log_record: OTELLogRecord) -> None:
        if log_record.timestamp is not None:
            self._collector_log_kwargs["time_unix_nano"] = log_record.timestamp

    def _translate_span_id(self, log_record: OTELLogRecord) -> None:
        self._collector_log_kwargs["span_id"] = log_record.span_id.to_bytes(
            8, "big"
        )

    def _translate_trace_id(self, log_record: OTELLogRecord) -> None:
        self._collector_log_kwargs["trace_id"] = log_record.trace_id.to_bytes(
            16, "big"
        )

    def _translate_trace_flags(self, log_record: OTELLogRecord) -> None:
        self._collector_log_kwargs["flags"] = int(log_record.trace_flags)

    def _translate_body(self, log_record: OTELLogRecord) -> None:
        self._collector_log_kwargs["body"] = log_record.body

    def _translate_severity_text(self, log_record: OTELLogRecord) -> None:
        self._collector_log_kwargs["severity_text"] = log_record.severity_text

    def _translate_attributes(self, log_record: OTELLogRecord) -> None:
        if log_record.attributes:
            self._collector_log_kwargs["attributes"] = []
            for key, value in log_record.attributes.items():
                try:
                    self._collector_log_kwargs["attributes"].append(
                        _translate_key_values(key, value)
                    )
                except Exception:  # pylint: disable=broad-except
                    _logger.warning(
                        "Exception while encoding key-value (%s-%s)",
                        key,
                        value,
                    )

    def _translate_data(
        self, batch: Sequence[OTELLogRecord]
    ) -> ExportLogsServiceRequest:
        # pylint: disable=attribute-defined-outside-init

        sdk_resource_instrumentation_library_logs = {}

        for log_data in batch:
            log_record = log_data.log_record
            instrumentation_info = log_data.instrumentation_info

            if log_record.resource not in (
                sdk_resource_instrumentation_library_logs.keys()
            ):
                if instrumentation_info is not None:
                    instrumentation_library_logs = InstrumentationLibraryLogs(
                        instrumentation_library=InstrumentationLibrary(
                            name=instrumentation_info.name,
                            version=instrumentation_info.version,
                        )
                    )

                else:
                    instrumentation_library_logs = InstrumentationLibraryLogs()

                sdk_resource_instrumentation_library_logs[
                    log_record.resource
                ] = instrumentation_library_logs

            self._collector_log_kwargs = {}

            self._translate_name(log_record)
            self._translate_time(log_record)
            self._translate_span_id(log_record)
            self._translate_trace_id(log_record)
            self._translate_trace_flags(log_record)
            self._translate_body(log_record)
            self._translate_severity_text(log_record)
            self._translate_attributes(log_record)

            self._collector_log_kwargs["severity_number"] = getattr(
                SeverityNumber,
                "SEVERITY_NUMBER_{}".format(log_record.severity_text),
            )

            sdk_resource_instrumentation_library_logs[
                log_data.resource
            ].logs.append(PB2LogRecord(**self._collector_log_kwargs))

        return ExportLogsServiceRequest(
            resource_logs=get_resource_data(
                sdk_resource_instrumentation_library_logs,
                ResourceLogs,
                "logs",
            )
        )

    def export(self, logs: Sequence[OTELLogRecord]) -> LogExportResult:
        return self._export(logs)
