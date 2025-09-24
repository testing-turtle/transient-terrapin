import logging
import os
from azure.monitor.opentelemetry.exporter import AzureMonitorLogExporter
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import (
    LoggerProvider,
    LoggingHandler,
)
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .trace_exporter import WorkflowTraceExporter



def configure_telemetry():
    # https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration?tabs=python#set-the-cloud-role-name-and-the-cloud-role-instance
    if not os.getenv("OTEL_RESOURCE_ATTRIBUTES"):
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = "service.namespace=gh-webhook,service.instance.id=an_instance"
    if not os.getenv("OTEL_SERVICE_NAME"):
        os.environ["OTEL_SERVICE_NAME"] = "gh-webhook"


    # https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/monitor/azure-monitor-opentelemetry-exporter
    logger_provider = LoggerProvider()
    set_logger_provider(logger_provider)
    log_exporter = AzureMonitorLogExporter(
        connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
    )
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    # Attach LoggingHandler to namespaced logger
    handler = LoggingHandler()
    logger = logging.getLogger(__name__)
    logger.addHandler(handler)
    logger.setLevel(logging.NOTSET)


    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    tracer = trace.get_tracer(__name__)
    # This is the exporter that sends data to Application Insights
    # trace_exporter = AzureMonitorTraceExporter(
    trace_exporter = WorkflowTraceExporter(
        connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
    )
    span_processor = BatchSpanProcessor(trace_exporter)
    # trace.get_tracer_provider().add_span_processor(span_processor)
    tracer_provider.add_span_processor(span_processor)

    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:\t%(message)s')

    logging.getLogger("azure.core").setLevel(logging.WARNING)
    logging.getLogger("azure.monitor").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


