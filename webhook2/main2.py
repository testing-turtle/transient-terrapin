from datetime import datetime
import logging
import os

from opentelemetry import trace
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from typing import Any
from telemetry import configure_telemetry, parse_date_time, to_ns_time_value
from github_webhook import verify_signature

print("Starting...")
load_dotenv()

configure_telemetry()

logger = logging.getLogger("gh-webhook")
logger.setLevel(logging.DEBUG)
tracer = trace.get_tracer("gh-webhook")


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
        organization = body_json.get("organization", {}).get("login")
        repository = body_json.get("repository", {}).get("name")

        parent_run_id = None
        parent_run_number = None
        parent_run_attempt = None
        if name.startswith("helper:"):
            # parse the name parts
            parts = name.split("-")
            parent_run_id = parts[1]
            parent_run_number = parts[2]
            parent_run_attempt = parts[3]
            logger.info(f"**************Helper workflow run detected. Parent Run ID: {parent_run_id}, Parent Run Number: {parent_run_number}, Parent Run Attempt: {parent_run_attempt}")


        # Create the workflow run span
        # Override the start time from the payload
        # The run_id and run_attempt will be used to correlate the workflow run with the jobs
        span = tracer.start_span(f"Workflow Run {name} ({run_key})",
                                 kind=trace.SpanKind.SERVER,
                                 start_time=to_ns_time_value(start_time),
                                 attributes={
            "organization": organization,
            "repository": repository,
            "run_id": id,
            "run_attempt": run_attempt,
            "event": run_event,
            "workflow_name": name,
            "type": "workflow_run",
            "http.url": "http://example.com",
            "conclusion": conclusion or "",
            "parent_run_id": parent_run_id,
            "parent_run_attempt": parent_run_attempt,
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
    organization = body_json.get("organization", {}).get("login")
    repository = body_json.get("repository", {}).get("name")
    workflow_name = body_json.get("workflow_job", {}).get("workflow_name")

    span: trace.Span | None = None
    start_time_string: str | None = None
    end_time_string: str | None = None
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

    parent_run_id = None
    parent_run_number = None
    parent_run_attempt = None
    if workflow_name.startswith("helper:"):
        # parse the name parts
        parts = workflow_name.split("-")
        parent_run_id = parts[1]
        parent_run_number = parts[2]
        parent_run_attempt = parts[3]
        logger.info(f"**************Helper workflow job detected. Parent Run ID: {parent_run_id}, Parent Run Number: {parent_run_number}, Parent Run Attempt: {parent_run_attempt}")


    # Start a new span for the workflow job
    # Override the start time from the payload
    # The run_id and run_attempt will be used to correlate the workflow job with the relevant workflow run
    span = tracer.start_span(
        f"Workflow Job {name} ({id}) {description}",
        kind=trace.SpanKind.CLIENT,
        start_time=to_ns_time_value(parse_date_time(start_time_string)),
        attributes={
            "organization": organization,
            "repository": repository,
            "job_id": id,
            "run_id": run_id,
            "action": action,
            "run_attempt": run_attempt,
            "job_name": name,
            "type": "workflow_job",
            "runner_id": runner_id,
            "parent_run_id": parent_run_id,
            "parent_run_attempt": parent_run_attempt,
        }
    )
    logger.info(f"Logging span for workflow job {id} {description} ***")
    span.end(end_time=to_ns_time_value(parse_date_time(end_time_string)))

    return 200, {"message": f"Workflow job {id} {action} processed successfully."}
