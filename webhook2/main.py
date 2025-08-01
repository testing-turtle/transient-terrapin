import json
import hashlib
import hmac
import logging
import os

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from typing import Union

load_dotenv()
configure_azure_monitor(
    logger_name="gh-webhook"
)
logger = logging.getLogger("gh-webhook")
tracer = trace.get_tracer("gh-webhook")

os.environ["OTEL_RESOURCE_ATTRIBUTES"] = "service.namespace=gh-webhook,service.instance.id=an_instance"

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


# store workflow run spans keyed on f"{run_id}#{run_attempt}"
workflow_run_spans: dict[str, trace.Span] = {}
# store workflow run queued job events keyed on f"{run_id}#{run_attempt}"
workflow_run_queued_job_events: dict[str, list] = {}
# store IDs of currently running jobs for a workflow run keyed on f"{run_id}#{run_attempt}"
workflow_run_current_jobs: dict[str, set] = {}
# store if a workflow run can complete keyed on f"{run_id}#{run_attempt}"
workflow_run_can_complete: dict[str, bool] = {}

# store workflow job spans keyed on job_id
workflow_job_spans: dict[str, trace.Span] = {}


@app.get("/ping")
def ping():
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
    logger.info(f'X-Forwarded-For: {x_forwarded_for}')

    event = req.headers.get('x-github-event')

    # logger.info(f'Got webhook event. Type: {event}. Payload: {body}')
    logger.info(f'Got webhook event. Type: {event}')

    if event == "workflow_run":
        # https://docs.github.com/en/webhooks/webhook-events-and-payloads?actionType=in_progress#workflow_run
        id = body_json.get("workflow_run", {}).get("id")
        run_attempt = body_json.get("workflow_run", {}).get("run_attempt")
        run_key = f"{id}#{run_attempt}"
        action = body_json.get("action")
        run_event = body_json.get("workflow_run", {}).get("event")
        name = body_json.get("workflow_run", {}).get("name")
        conclusion = body_json.get("workflow_run", {}).get("conclusion")
        span: trace.Span | None = None
        complete_span = False
        if action == "in_progress":
            if run_key in workflow_run_spans:
                logger.info(
                    f"Workflow run span for run_key {run_key} already exists. Ignoring event.")
                resp.status_code = 200
                return {"message": f"Workflow run span for run_key {run_key} already exists. Ignoring event."}

            # Start a new span for the workflow run
            span = tracer.start_span(f"Workflow Run {run_key} {action}",
                                     kind=trace.SpanKind.SERVER,
                                     attributes={
                                         "run_id": id,
                                         "attempt": run_attempt,
                                         "event": run_event,
                                         "workflow_name": name,
                                         "type": "workflow_run",
                                         "http.url": "http://example.com"
            })
            logger.info(
                f"*** starting span for workflow run {run_key} in_progress ***")
            workflow_run_spans[run_key] = span
        else:
            # End the span for the workflow run if it exists
            # TODO - the workflow end event can come before the events for the completion of workflow jobs for the run
            #        so we need to track the running jobs for a workflow run and only mark the run as complete when all jobs are done
            span = workflow_run_spans.pop(run_key, None)
            if span:
                span.set_attribute("conclusion", conclusion or "")
                jobs = workflow_run_current_jobs.pop(run_key, set())
                if len(jobs) > 0:
                    logger.info(
                        f"Workflow run {run_key} has jobs running ({jobs}). Cannot mark run as complete yet.")
                    # indicate that we can complete the run when all jobs are done
                    workflow_run_can_complete[run_key] = True
                else:
                    complete_span = True
                    logger.info(
                        f"*** marking to end span for workflow run {run_key} {action} ***")

        if not span:
            logger.error(
                f"Span for workflow run {run_key} not found. This is unexpected.")
            resp.status_code = 500
            return {"message": f"Span for workflow run {run_key} not found. This is unexpected."}


        logger.info("### workflow_run event. ID: %s, TraceID: %s, Action: %s",
                    run_key, span.get_span_context().trace_id, action)

        with trace.use_span(span, end_on_exit=complete_span) as span:
            if workflow_run_queued_job_events.get(run_key):
                logger.info(
                    f"Processing queued job events for workflow run {run_key}.")
                # Process any queued job events for this run
                for queued_event in workflow_run_queued_job_events[run_key]:
                    process_workflow_job_event(queued_event)
                # Clear the queued events after processing
                del workflow_run_queued_job_events[run_key]

            logger.info(f"Workflow run {run_key} {action}",
                        extra={
                            "microsoft.custom_event.name": "webhook",
                            "event": event,
                            "run_id": id,
                            "run_attempt": run_attempt,
                            "action": action,
                            "run_event": run_event,
                            "workflow_name": name,
                            "conclusion": conclusion or ""
            })

    elif event == "workflow_job":
        # https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_job
        run_id = body_json.get("workflow_job", {}).get("run_id")
        run_attempt = body_json.get("workflow_job", {}).get("run_attempt")
        run_key = f"{run_id}#{run_attempt}"
        # TODO - is run_id unique or do we need to include run_attempt?

        workflow_run_span = workflow_run_spans.get(
            run_key)  # TODO - handle not existing
        if not workflow_run_span:
            logger.info(
                f"Workflow run span for run_id {run_key} not found. Storing event for later processing.")
            job_events = workflow_run_queued_job_events.get(run_key, [])
            job_events.append(body_json)
            workflow_run_queued_job_events[run_key] = job_events
            resp.status_code = 200
            return {"message": f"Workflow run span for run_id {run_key} not found. Storing event for later processing."}

        logger.info("### workflow_job event. Run ID: %s, Run TraceID: %s",
                    run_key, workflow_run_span.get_span_context().trace_id)

        with trace.use_span(workflow_run_span, end_on_exit=False) as workflow_run_span:
            # Process the workflow job event
            logger.info(f"Processing workflow job event for run_id {run_key}.")
            process_workflow_job_event(body_json)
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


def process_workflow_job_event(body_json):

    id = body_json.get("workflow_job", {}).get("id")
    action = body_json.get("action")
    run_id = body_json.get("workflow_job", {}).get("run_id")
    run_attempt = body_json.get("workflow_job", {}).get("run_attempt")
    run_key = f"{run_id}#{run_attempt}"
    runner_id = body_json.get("workflow_job", {}).get("runner_id")
    conclusion = body_json.get("workflow_job", {}).get("conclusion")
    name = body_json.get("workflow_job", {}).get("name")

    span: trace.Span | None = None
    end_on_exit = False
    if action == "queued":
        # Start a new span for the workflow job
        span = tracer.start_span(f"Workflow Job {id} {action}",
                                 kind=trace.SpanKind.CLIENT,
                                 attributes={
            "job_id": id,
            "run_id": run_id,
            "action": action,
            "run_attempt": run_attempt,
            "job_name": name,
            "type": "workflow_job"
        })
        logger.info(f"*** starting span for workflow job {id} queued ***")
        workflow_job_spans[id] = span
    elif action == "in_progress":
        # End the queued span and start a new one for in_progress
        span = workflow_job_spans.get(id)
        if span:
            logger.info(f"*** ending span for workflow job {id} queued ***")
            span.end()
        span = tracer.start_span(f"Workflow Job {id} {action}",
                                 kind=trace.SpanKind.CLIENT,
                                 attributes={
            "job_id": id,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "action": action,
            "run_attempt": run_attempt,
            "job_name": name,
            "runner_id": runner_id,
            "type": "workflow_job"
        })
        logger.info(f"*** starting span for workflow job {id} in_progress ***")
        workflow_job_spans[id] = span
    elif action == "completed":
        if conclusion == "skipped":
            # no start event for the job, so skip for now
            # TODO - continue to emit the event for the skipped jobs and associate with the workflow run span
            logger.info(f"Workflow job {id} skipped.")
            return
        span = workflow_job_spans.get(id)
        if span:
            span.set_attribute("conclusion", conclusion or "")
            end_on_exit = True
            logger.info(
                f"*** marking to end span for workflow job {id} completed ***")
    else:
        logger.warning(
            f"Unknown action {action} for workflow job {id}. Payload: {body_json}")

    if not span:
        logger.error(
            f"Span for workflow job {id} not found. This is unexpected.")
        return

    logger.info("### workflow_job event. ID: %s, TraceID: %s, Action: %s",
                id, span.get_span_context().trace_id, action)

    with trace.use_span(span, end_on_exit=end_on_exit) as span:
        logger.info(f"Workflow job {id} {action}",
                    extra={
                        "microsoft.custom_event.name": "webhook",
                        "event": "workflow_job",
                        "job_id": id,
                        "action": action,
                        "run_id": run_id,
                        "run_attempt": run_attempt,
                        "runner_id": runner_id or "",
                        "conclusion": conclusion or "",
                        "run_attempt": run_attempt,
                        "job_name": name
        })

    if end_on_exit:
        # If the span is ending, we can remove it from the jobs for the workflow run
        jobs = workflow_run_current_jobs.get(run_key, set())
        jobs.discard(id)
        logger.info(
            f"!!! Workflow run {run_key} has {len(jobs)} jobs running. [discarded {id}]")
        if len(jobs) == 0 and workflow_run_can_complete.get(run_key, False):
            # If there are no more jobs running for this workflow run, we can mark it as complete
            logger.info(
                f"All jobs for workflow run {run_key} are complete. Marking run as complete.")
            workflow_run_can_complete[run_key] = True
            span = workflow_run_spans.get(run_key)
            if span:
                span.end()
    else:
        jobs = workflow_run_current_jobs.setdefault(run_key, set())
        jobs.add(id)
        workflow_run_current_jobs[run_key] = jobs
        logger.info(
            f"!!! Workflow run {run_key} has {len(jobs)} jobs running. [added {id}]")
