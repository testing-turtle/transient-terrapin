import asyncio
from dataclasses import dataclass, field
import hashlib
import hmac
import logging
import os

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from typing import Any, Union

print("Starting...")
load_dotenv()

# https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration?tabs=python#set-the-cloud-role-name-and-the-cloud-role-instance
if not os.getenv("OTEL_RESOURCE_ATTRIBUTES"):
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = "service.namespace=gh-webhook,service.instance.id=an_instance"
if not os.getenv("OTEL_SERVICE_NAME"):
    os.environ["OTEL_SERVICE_NAME"] = "gh-webhook"

configure_azure_monitor(
    logger_name="gh-webhook"
)
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


@dataclass
class WorkflowRunState:
    """Class to hold the state of a workflow run."""
    lock: asyncio.Lock  # guard updates to this state
    span: trace.Span  | None # nullable to enable queing events before the span is created by the run event
    queued_job_events: list = field(default_factory=list)
    job_spans: dict[str, trace.Span] = field(default_factory=dict)  # keyed on job_id
    current_jobs: set = field(default_factory=set)  # TODO - can we remove this and just use job_spans to track?
    can_complete: bool = False
    completed: bool = False  # indicates if the workflow run has completed


class WebHookState:
    """Class to hold the state of the webhook processing. asyncio.locks are used to ensure thread safety."""

    # _workflow_run_locks: dict[str, asyncio.Lock] = {}
    # guard updates to _workflow_run_states
    _state_lock: asyncio.Lock = asyncio.Lock()
    # keyed on f"{run_id}#{run_attempt}"
    _workflow_run_states: dict[str, WorkflowRunState] = {}

    def __init__(self):
        pass

    async def get_workflow_run_state(self, run_id: str, run_attempt: Union[int, str]) -> WorkflowRunState | None:
        """Get the workflow run state for the given run_id and run_attempt."""
        async with self._state_lock:
            run_key = f"{run_id}#{run_attempt}"
            return self._workflow_run_states.get(run_key, None)

    async def add_workflow_run_state(self, run_id: str, run_attempt: Union[int, str], state: WorkflowRunState) -> tuple[WorkflowRunState, bool]:
        """
            Add a new workflow run state for the given run_id and run_attempt.
            If the state already exists, return the existing state and False.
            If the state is added, return the new state and True.
        """
        async with self._state_lock:
            run_key = f"{run_id}#{run_attempt}"
            if run_key in self._workflow_run_states:
                return self._workflow_run_states[run_key], False
            self._workflow_run_states[run_key] = state
            return self._workflow_run_states[run_key], True

    async def remove_workflow_run_state(self, run_id: str, run_attempt: Union[int, str]):
        """Remove the workflow run state for the given run_id and run_attempt."""
        async with self._state_lock:
            run_key = f"{run_id}#{run_attempt}"
            if run_key not in self._workflow_run_states:
                raise ValueError(
                    f"Workflow run state for {run_key} not found.")
            del self._workflow_run_states[run_key]


webhook_state = WebHookState()


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
    logger.info(f'Got webhook event. Type: {event}. Action: {body_json.get("action")}. Conclusion: {body_json.get("conclusion")}')

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



async def handle_workflow_run_event(body_json: Any) -> tuple[int, dict]:
    # https://docs.github.com/en/webhooks/webhook-events-and-payloads?actionType=in_progress#workflow_run
    id = body_json.get("workflow_run", {}).get("id")
    run_attempt = body_json.get("workflow_run", {}).get("run_attempt")
    run_key = f"{id}#{run_attempt}"
    action = body_json.get("action")
    run_event = body_json.get("workflow_run", {}).get("event")
    name = body_json.get("workflow_run", {}).get("name")
    conclusion = body_json.get("workflow_run", {}).get("conclusion")
    complete_span = False
    run_state: WorkflowRunState | None = None
    if action == "in_progress":
        #
        # Scenarios:
        # 1. If this is the first event for the workflow run, we will not have any run state yet.
        # 2. If we have seen job events for this run, we will have a run state, but no span yet.
        # 3. It is also possible to get an in_progress event for a run that we have already seen and processed.
        #
        # For scenario 1, we will create a new run state and start a new span.
        # For scenario 2, we will create a new span and associate it with the run. We also need to process any queued job events for this run.
        # For scenario 3, we will ignore the event if the span already exists.
        #
        run_state = await webhook_state.get_workflow_run_state(run_id=id, run_attempt=run_attempt)
        span: trace.Span | None = None
        if run_state:
            if run_state.span:
                logger.info(
                    f"Workflow run span for run_key {run_key} already exists. Ignoring in_progress event.")
                return 200, {"message": f"Workflow run span for run_key {run_key} already exists. Ignoring in_progress event."}

            # We have a run state, but no span yet.
            # Start a new span for the workflow run
            span = tracer.start_span(f"Workflow Run {run_key}",
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
        
        if not run_state:
            run_state = WorkflowRunState(
                lock=asyncio.Lock(),
                span=span,
            )
            run_state, created = await webhook_state.add_workflow_run_state(run_id=id, run_attempt=run_attempt, state=run_state)
            if created:
                logger.info(f"Created new workflow run state for {run_key}.")
            else:
                logger.info(
                    f"Workflow run state for {run_key} already exists. Ignoring event.")
                return 200, {"message": f"Workflow run state for {run_key} already exists. Ignoring event."}
        
        async with run_state.lock:
            if span:
                # we created a new span above, so set it on the run state (now that we're in the lock)
                run_state.span = span

            logger.info(f"Created new workflow run state for {run_key}.")
            process_workflow_run_event(run_state, id, run_attempt, action, run_event, name, conclusion, complete_span)
            return 200, {"message": f"Workflow run state for {run_key} created and event processed."}
    elif action == "completed":
        # End the span for the workflow run if it exists
        # Note that the workflow end event can come before the events for the completion of workflow jobs for the run
        # so we need to track the running jobs for a workflow run and only mark the run as complete when all jobs are done
        run_state = await webhook_state.get_workflow_run_state(run_id=id, run_attempt=run_attempt)
        if not run_state:
            logger.error(
                f"Workflow run state for {run_key} not found. This is unexpected.")
            return 500, {"message": f"Workflow run state for {run_key} not found. This is unexpected."}

        if not run_state.span:
            logger.error(
                f"Workflow run span for {run_key} not found. This is unexpected.")
            return 500, {"message": f"Workflow run span for {run_key} not found. This is unexpected."}

        async with run_state.lock:
            run_state.span.set_attribute("conclusion", conclusion or "")

            span = run_state.span
            if not span:
                logger.error(
                    f"Span for workflow run {run_key} not found. This is unexpected.")
                return 500, {"message": f"Span for workflow run {run_key} not found. This is unexpected."}
            
            span.set_attribute("conclusion", conclusion or "")
            jobs = run_state.current_jobs
            if len(jobs) > 0:
                logger.info(
                    f"Workflow run {run_key} has jobs running ({jobs}). Cannot mark run as complete yet.")
                # indicate that we can complete the run when all jobs are done
                run_state.can_complete = True
            else:
                complete_span = True
                logger.info(
                    f"Marking to end span for workflow run {run_key} {action} ***")
                    
            process_workflow_run_event(run_state, id, run_attempt, action, run_event, name, conclusion, complete_span)

        if run_state.completed:
            # If the run state is completed, we can remove it from the dict
            # NOTE: this must be outside the runstate_lock to avoid deadlocks
            await webhook_state.remove_workflow_run_state(run_id=id, run_attempt=run_attempt)
            logger.info(f"Workflow run state for {run_key} removed after completion.")

        return 200, {"message": f"Workflow run {run_key} {action} processed successfully."}
    else:
        logger.warning(
            f"Unknown action {action} for workflow run {run_key}. Payload: {body_json}")
        return 400, {"message": f"Unknown action {action} for workflow run {run_key}."}

def process_workflow_run_event(run_state: WorkflowRunState, run_id: str, run_attempt: str, action: str, run_event: str, name: str, conclusion: str, complete_span: bool) -> tuple[int, dict]:

    run_key = f"{run_id}#{run_attempt}"

    if not run_state or not run_state.span:
        logger.error(
            f"Span for workflow run {run_key} not found. This is unexpected.")
        return 500, {"message": f"Span for workflow run {run_key} not found. This is unexpected."}

    logger.debug("### workflow_run event. ID: %s, TraceID: %s, Action: %s",
                run_key, run_state.span.get_span_context().trace_id, action)

    with trace.use_span(run_state.span, end_on_exit=complete_span) as span:
        if run_state.queued_job_events:
            logger.info(
                f"Processing queued job events for workflow run {run_key}.")
            # Process any queued job events for this run
            for queued_event in run_state.queued_job_events:
                process_workflow_job_event(queued_event, workflow_run_state=run_state)
            # Clear the queued events after processing
            run_state.queued_job_events.clear()

        # Create a Custom Event for the workflow run
        logger.info(f"Workflow run {run_key} {action}",
                    extra={
                        "microsoft.custom_event.name": "webhook",
                        "event": "workflow_run",
                        "run_id": run_id,
                        "run_attempt": run_attempt,
                        "action": action,
                        "run_event": run_event,
                        "workflow_name": name,
                        "conclusion": conclusion or ""
        })

    if complete_span:
        run_state.completed = True

    return (200, {"message": f"Workflow run {run_key} {action} processed successfully."})


async def handle_workflow_job_event(body_json: Any) -> tuple[int, dict]:
    # https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_job
    run_id = body_json.get("workflow_job", {}).get("run_id")
    run_attempt = body_json.get("workflow_job", {}).get("run_attempt")
    run_key = f"{run_id}#{run_attempt}"

    run_state = await webhook_state.get_workflow_run_state(run_id=run_id, run_attempt=run_attempt)
    if not run_state:
        run_state = WorkflowRunState(
            lock=asyncio.Lock(),
            span=None,  # This will be set when the workflow run is created
        )
        run_state.queued_job_events.append(body_json)
        run_state, created = await webhook_state.add_workflow_run_state(
            run_id=run_id, run_attempt=run_attempt, state=run_state)
        if not created:
            # another request has created the workflow run state
            # re-run this function to process the event
            logger.info(
                f"Workflow run state for {run_key} already exists. Re-processing event.")
            return await handle_workflow_job_event(body_json)
        return 200, {"message": f"Workflow run state for {run_key} created and event queued for processing."}

    async with run_state.lock:
        
        workflow_run_span = run_state.span
        if not workflow_run_span:
            logger.info(
                f"Workflow run span for run_id {run_key} not found. Storing event for later processing.")
            run_state.queued_job_events.append(body_json)
            return 200, {"message": f"Workflow run span for run_id {run_key} not found. Storing event for later processing."}

        logger.debug("### workflow_job event. Run ID: %s, Run TraceID: %s",
                    run_key, workflow_run_span.get_span_context().trace_id)

        with trace.use_span(workflow_run_span, end_on_exit=False) as workflow_run_span:
            # Process the workflow job event
            logger.info(f"Processing workflow job event for run_id {run_key}.")
            process_workflow_job_event(body_json, run_state )

    if run_state.completed:
        # If the run state is completed, we can remove it from the dict
        # NOTE: this must be outside the runstate_lock to avoid deadlocks
        await webhook_state.remove_workflow_run_state(run_id=run_id, run_attempt=run_attempt)
        logger.info(f"Workflow run state for {run_key} removed after completion.")

    return 200, {"message": f"Workflow job event for run_id {run_key} processed successfully."}


def process_workflow_job_event(body_json, workflow_run_state: WorkflowRunState):
    """
    Process a workflow job event and update the workflow run state.
    The lock should on the workflow_run_state should be acquired before calling this function.
    """
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
        span = tracer.start_span(f"Workflow Job {id} queuing",
                                 kind=trace.SpanKind.CLIENT,
                                 attributes={
            "job_id": id,
            "run_id": run_id,
            "action": action,
            "run_attempt": run_attempt,
            "job_name": name,
            "type": "workflow_job"
        })
        logger.info(f"Starting span for workflow job {id} queued ***")
        workflow_run_state.job_spans[id] = span
    elif action == "in_progress":
        # End the queued span and start a new one for in_progress
        span = workflow_run_state.job_spans.get(id)
        if span:
            logger.info(f"Ending span for workflow job {id} queued ***")
            span.end()
        span = tracer.start_span(f"Workflow Job {id} running",
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
        logger.info(f"Starting span for workflow job {id} in_progress ***")
        workflow_run_state.job_spans[id] = span
    elif action == "completed":
        if conclusion == "skipped":
            # no start event for the job, so skip for now
            # TODO - continue to emit the event for the skipped jobs and associate with the workflow run span
            logger.info(f"Workflow job {id} skipped.")
            return
        span = workflow_run_state.job_spans.get(id)
        if span:
            span.set_attribute("conclusion", conclusion or "")
            end_on_exit = True
            logger.info(
                f"Marking to end span for workflow job {id} completed ***")
    else:
        logger.warning(
            f"Unknown action {action} for workflow job {id}. Payload: {body_json}")

    if not span:
        logger.error(
            f"Span for workflow job {id} not found. This is unexpected.")
        return

    logger.debug("### workflow_job event. ID: %s, TraceID: %s, Action: %s",
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
        workflow_run_state.current_jobs.discard(id)
        logger.info(
            f"Workflow run {run_key} has {len(workflow_run_state.current_jobs)} jobs running. [discarded {id}]")
        if len(workflow_run_state.current_jobs) == 0 and workflow_run_state.can_complete:
            # If there are no more jobs running for this workflow run, we can mark it as complete
            logger.info(
                f"All jobs for workflow run {run_key} are complete. Marking run as complete.")
            span = workflow_run_state.span
            if span:
                span.end()
                workflow_run_state.completed = True
                # TODO - remove the workflow run state from the dict (avoid deadlock!)
    else:
        workflow_run_state.current_jobs.add(id)
        logger.info(
            f"Workflow run {run_key} has {len(workflow_run_state.current_jobs)} jobs running. [added {id}]")
