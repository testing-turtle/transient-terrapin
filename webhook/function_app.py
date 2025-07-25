import azure.functions as func
import hashlib
import hmac
import logging
import os

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from dotenv import load_dotenv

load_dotenv()
configure_azure_monitor(
    logger_name="gh-webhook"
)
logger = logging.getLogger("gh-webhook")
tracer = trace.get_tracer("gh-webhook")

secret_token = os.getenv("WEBHOOK_SECRET")
if not secret_token:
    raise ValueError("WEBHOOK_SECRET environment variable is not set.")


# https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
# https://github.com/github/docs/blob/main/content/webhooks/using-webhooks/validating-webhook-deliveries.md


# https://docs.github.com/en/webhooks/webhook-events-and-payloads#ping

# Get IP addresses for GitHub: https://docs.github.com/en/rest/meta/meta?apiVersion=2022-11-28#get-github-meta-information

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


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="ping")
def ping(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Got a ping.')

    return func.HttpResponse("pong", status_code=200)


workflow_run_spans = {} # store workflow run spans keyed on run_id
workflow_job_spans = {} # store workflow job spans keyed on job_id

@app.route(route="{ignored:maxlength(0)?}")
def webhook(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Webhook triggered.')

    body = req.get_body()

    verify_signature_status, verify_message = verify_signature(
        payload_body=body,
        secret_token=secret_token or "",
        headers=req.headers
    )
    if verify_signature_status:
        logging.error(f"Signature verification failed: {verify_message}")
        return func.HttpResponse(verify_message, status_code=verify_signature_status)

    event = req.headers.get('x-github-event')

    logging.info(f'Got webhook event. Type: {event}. Payload: {body}')

    body_json = req.get_json()
    
    # NOTE: this is experimental code and is likely buggy!
    # For example, it currently assumes that events are delivered in order,
    # which is likely not the case in practice.

    if event == "workflow_run":
        # https://docs.github.com/en/webhooks/webhook-events-and-payloads?actionType=in_progress#workflow_run
        id = body_json.get("workflow_run", {}).get("id")
        action = body_json.get("action")
        run_event = body_json.get("workflow_run", {}).get("event")
        name = body_json.get("workflow_run", {}).get("name")
        conclusion = body_json.get("workflow_run", {}).get("conclusion")
        if action == "in_progress":
            # Start a new span for the workflow run
            span = tracer.start_span(f"Workflow Run {id} {action}",
                                     kind=trace.SpanKind.SERVER,
                                     attributes={
                                         "run_id": id,
                                         "event": run_event,
                                         "workflow_name": name,
                                         "type": "workflow_run"
                                     })
            workflow_run_spans[id] = span
        else:
            # End the span for the workflow run if it exists
            span = workflow_run_spans.pop(id, None)
            if span:
                span.set_attribute("conclusion", conclusion or "")
                span.end()
        
        # TODO - ideally the event would be added within the span context.
        logger.info(f"Workflow run {id} {action}",
                    extra={
                        "microsoft.custom_event.name": "webhook",
                        "event": event,
                        "run_id": id,
                        "action": action,
                        "run_event": run_event,
                        "workflow_name": name,
                        "conclusion": conclusion or ""
        })
    elif event == "workflow_job":
        # https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_job
        id = body_json.get("workflow_job", {}).get("id")
        action = body_json.get("action")
        run_id = body_json.get("workflow_job", {}).get("run_id")
        runner_id = body_json.get("workflow_job", {}).get("runner_id")
        conclusion = body_json.get("workflow_job", {}).get("conclusion")
        run_attempt = body_json.get("workflow_job", {}).get("run_attempt")
        name = body_json.get("workflow_job", {}).get("name")

        
        workflow_run_span = workflow_run_spans.get(run_id) # TODO - handle not existing
        if action == "queued":
            # Start a new span for the workflow job
            span = tracer.start_span(f"Workflow Job {id} {action}", 
                                     context=trace.set_span_in_context(workflow_run_span),
                                     kind=trace.SpanKind.CLIENT,
                                     attributes={
                                         "job_id": id,
                                         "run_id": run_id,
                                         "action": action,
                                         "run_attempt": run_attempt,
                                         "job_name": name,
                                         "type": "workflow_job"
                                     })
            workflow_job_spans[id] = span
        elif action == "in_progress":
            # End the queued span and start a new one for in_progress
            span = workflow_job_spans.get(id)
            if span:
                span.end()
            span = tracer.start_span(f"Workflow Job {id} {action}", 
                                     context=trace.set_span_in_context(workflow_run_span),
                                     kind=trace.SpanKind.CLIENT,
                                     attributes={
                                         "job_id": id,
                                         "run_id": run_id,
                                         "action": action,
                                         "run_attempt": run_attempt,
                                         "job_name": name,
                                         "runner_id": runner_id,
                                         "type": "workflow_job"
                                     })
            workflow_job_spans[id] = span
        elif action == "completed":
            span = workflow_job_spans.get(id)
            if span:
                span.set_attribute("conclusion", conclusion or "")
                span.end()
        else:
            logger.warning(f"Unknown action {action} for workflow job {id}. Payload: {body_json}")

        logger.info(f"Workflow job {id} {action}",
                    extra={
                        "microsoft.custom_event.name": "webhook",
                        "event": event,
                        "job_id": id,
                        "action": action,
                        "run_id": run_id,
                        "runner_id": runner_id or "",
                        "conclusion": conclusion or "",
                        "run_attempt": run_attempt,
                        "job_name": name
        })
    else:
        # unknown event
        logger.warning(f"Unknown event type: {event}. Payload: {body_json}")


    return func.HttpResponse("Webhook received", status_code=200)
