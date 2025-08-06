from datetime import datetime
import json
import hashlib
import hmac
import logging
import os

from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter, AzureMonitorLogExporter
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import (
    LoggerProvider,
    LoggingHandler,
)
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry import trace
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from typing import Any

print("Starting...")
load_dotenv()


# https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration?tabs=python#set-the-cloud-role-name-and-the-cloud-role-instance
if not os.getenv("OTEL_RESOURCE_ATTRIBUTES"):
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = "service.namespace=gh-webhook,service.instance.id=an_instance"
if not os.getenv("OTEL_SERVICE_NAME"):
    os.environ["OTEL_SERVICE_NAME"] = "gh-webhook"


class CustomTraceExporter(AzureMonitorTraceExporter):
    """
    A custom trace exporter that extends AzureMonitorTraceExporter to modify the span to envelope conversion.
    This allows correlating the spans with workflow runs and jobs without needing to preserve the original spans in memory.
    """

    def _span_to_envelope(self, span):
        envelope = super()._span_to_envelope(span)
        # Add custom logic here if needed
        # print(f"Custom envelope for span: {span.name}. OperationId: {envelope.tags.get('ai.operation.id')}, Parent Id: {envelope.tags.get('ai.operation.parentId')}")
        print(json.dumps(envelope.tags, indent=2))
        # print(envelope)
        # print(envelope.data)
        # print(envelope.data.base_data)
        properties = envelope.data.base_data.properties
        run_id = properties.get("run_id", None)
        run_attempt = properties.get("run_attempt", None)
        if run_id and run_attempt:
            run_key = f"{run_id}#{run_attempt}"
            # we've got a run or a job
            # set the operation id to the run key
            envelope.tags["ai.operation.id"] = run_key
            job_id = properties.get("job_id", None)
            if job_id:
                # Got a job
                # set the parent id to the run key
                envelope.tags["ai.operation.parentId"] = run_key
                print(f"RunId: {run_id}\tJob ID: {job_id}")
            else:
                # No job id, so this is a run
                # set the ID to the run key (so that it can be used as a parent for jobs)
                envelope.data.base_data.id = run_key
                print(f"RunId: {run_id}\tNo Job ID")

        print(
            f"## envelope: OperationID: {envelope.tags.get('ai.operation.id')}\tID: {envelope.data.base_data.id}\tOperationParentId: {envelope.tags.get('ai.operation.parentId')} - SpanName: {span.name}")
        return envelope

    def _span_events_to_envelopes(self, span):
        envelopes = super()._span_events_to_envelopes(span)
        # Add custom logic here if needed
        print(f"Custom envelopes for span events: {span.name}")
        return envelopes


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
trace_exporter = CustomTraceExporter(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
)
span_processor = BatchSpanProcessor(trace_exporter)
# trace.get_tracer_provider().add_span_processor(span_processor)
tracer_provider.add_span_processor(span_processor)


logger = logging.getLogger("gh-webhook")
tracer = trace.get_tracer("gh-webhook")

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:\t%(message)s')

logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.monitor").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger.setLevel(logging.DEBUG)

secret_token = os.getenv("WEBHOOK_SECRET")
if not secret_token:
    raise ValueError("WEBHOOK_SECRET environment variable is not set.")

app = FastAPI()

# NOTE: this is experimental code and is likely buggy!
# There is some handling of out-of-order events, but all data is stored in memory and with no thought to concurrency


# https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
# https://github.com/github/docs/blob/main/content/webhooks/using-webhooks/validating-webhook-deliveries.md


# https://docs.github.com/en/webhooks/webhook-events-and-payloads#ping

# Get IP addresses for GitHub: https://docs.github.com/en/rest/meta/meta?apiVersion=2022-11-28#get-github-meta-information


@app.get("/ping")
def ping():
    logger.info("Ping received.")
    return {"Hello": "World"}


@app.post("/")
async def webhook(req: Request, resp: Response):
    body = await req.body()
    verify_signature_status, verify_message = verify_signature(
        payload_body=body,
        secret_token=secret_token or "",
        headers=req.headers
    )
    if verify_signature_status:
        logger.error(f"Signature verification failed: {verify_message}")
        resp.status_code = verify_signature_status
        return {"message": verify_message}

    body_json = await req.json()
    logger.info('Webhook triggered.')

    x_forwarded_for = req.headers.get('X-Forwarded-For')
    logger.debug(f'X-Forwarded-For: {x_forwarded_for}')

    event = req.headers.get('x-github-event')

    # logger.info(f'Got webhook event. Type: {event}. Payload: {body}')
    logger.info(
        f'Got webhook event. Type: {event}. Action: {body_json.get("action")}. Conclusion: {body_json.get("conclusion")}')

    if event == "workflow_run":
        status, result = await handle_workflow_run_event(body_json)
        resp.status_code = status
        return result
    elif event == "workflow_job":
        status, result = await handle_workflow_job_event(body_json)
        resp.status_code = status
        return result
    else:
        # unknown event
        logger.warning(f"Unknown event type: {event}. Payload: {body_json}")

    resp.status_code = 200
    return {"message": f"Webhook event {event} processed successfully."}


def verify_signature(payload_body, secret_token, headers):
    """Verify that the payload was sent from GitHub by validating SHA256.

    Raise and return 403 if not authorized.

    Args:
        payload_body: original request body to verify (request.body())
        secret_token: GitHub app webhook token (WEBHOOK_SECRET)
        signature_header: header received from GitHub (x-hub-signature-256)
    """

    signature_header = headers.get('x-hub-signature-256') if headers else None
    if not signature_header:
        return 403, "x-hub-signature-256 header is missing!"
    hash_object = hmac.new(secret_token.encode(
        'utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    if not hmac.compare_digest(expected_signature, signature_header):
        return 403, "Request signatures didn't match!"

    return None, None


def parse_date_time(date_time_string: str) -> datetime:
    return datetime.fromisoformat(date_time_string.replace("Z", "+00:00"))


def to_ns_time_value(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


async def handle_workflow_run_event(body_json: Any) -> tuple[int, dict]:
    # https://docs.github.com/en/webhooks/webhook-events-and-payloads?actionType=in_progress#workflow_run
    action = body_json.get("action")
    if action == "completed":
        id = body_json.get("workflow_run", {}).get("id")
        run_attempt = body_json.get("workflow_run", {}).get("run_attempt")
        run_key = f"{id}#{run_attempt}"
        run_event = body_json.get("workflow_run", {}).get("event")
        name = body_json.get("workflow_run", {}).get("name")
        conclusion = body_json.get("workflow_run", {}).get("conclusion")
        start_time_string = body_json.get(
            "workflow_run", {}).get("run_started_at")
        end_time_string = body_json.get("workflow_run", {}).get("updated_at")
        start_time = parse_date_time(start_time_string)
        end_time = parse_date_time(end_time_string)

        # Create the workflow run span
        # Override the start time from the payload
        # The run_id and run_attempt will be used to correlate the workflow run with the jobs
        span = tracer.start_span(f"Workflow Run {run_key}",
                                 kind=trace.SpanKind.SERVER,
                                 start_time=to_ns_time_value(start_time),
                                 attributes={
            "run_id": id,
            "run_attempt": run_attempt,
            "event": run_event,
            "workflow_name": name,
            "type": "workflow_run",
            "http.url": "http://example.com",
            "conclusion": conclusion or ""
        })

        # End the span with the end time from the payload
        span.end(end_time=to_ns_time_value(end_time))

        return 200, {"message": f"Workflow run {run_key} {action} processed successfully."}

    return 200, {"message": f"Action {action} ignored."}


async def handle_workflow_job_event(body_json: Any) -> tuple[int, dict]:
    # https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_job
    id = body_json.get("workflow_job", {}).get("id")
    action = body_json.get("action")
    run_id = body_json.get("workflow_job", {}).get("run_id")
    run_attempt = body_json.get("workflow_job", {}).get("run_attempt")
    runner_id = body_json.get("workflow_job", {}).get("runner_id")
    conclusion = body_json.get("workflow_job", {}).get("conclusion")
    name = body_json.get("workflow_job", {}).get("name")

    span: trace.Span | None = None
    start_time_string : str | None = None
    end_time_string : str | None = None
    description: str | None = None

    if action == "queued":
        return 200, {"message": f"Workflow job {id} queued - ignoring."}
    elif action == "in_progress":
        description = "queued"
        start_time_field = "created_at"
        end_time_field = "started_at"
    elif action == "completed":
        if conclusion == "skipped":
            # no start event for the job, so skip for now
            # TODO - continue to emit the event for the skipped jobs and associate with the workflow run span
            logger.info(f"Workflow job {id} skipped.")
            return 200, {"message": f"Workflow job {id} skipped."}
        description = "running"
        start_time_field = "started_at"
        end_time_field = "completed_at"
    else:
        logger.warning(
            f"Unknown action {action} for workflow job {id}. Payload: {body_json}")
        return 200, {"message": f"Action {action} ignored for workflow job {id}."}

    start_time_string = body_json.get("workflow_job", {}).get(start_time_field)
    end_time_string = body_json.get("workflow_job", {}).get(end_time_field)

    if not start_time_string:
        logger.warning(
            f"Start time not found for workflow job {id}. Payload: {body_json}")
        return 400, {"message": f"Start time not found for workflow job {id}."}
    
    if not end_time_string:
        logger.warning(
            f"End time not found for workflow job {id}. Payload: {body_json}")
        return 400, {"message": f"End time not found for workflow job {id}."}
    
    # Start a new span for the workflow job
    # Override the start time from the payload
    # The run_id and run_attempt will be used to correlate the workflow job with the relevant workflow run
    span = tracer.start_span(
        f"Workflow Job {id} {description}",
        kind=trace.SpanKind.CLIENT,
        start_time=to_ns_time_value(parse_date_time(start_time_string)),
        attributes={
            "job_id": id,
            "run_id": run_id,
            "action": action,
            "run_attempt": run_attempt,
            "job_name": name,
            "type": "workflow_job",
            "runner_id": runner_id,
        }
    )
    logger.info(f"Logging span for workflow job {id} {description} ***")
    span.end(end_time=to_ns_time_value(parse_date_time(end_time_string)))

    return 200, {"message": f"Workflow job {id} {action} processed successfully."}
