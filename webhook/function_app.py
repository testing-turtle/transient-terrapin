import azure.functions as func
import hashlib
import hmac
import logging
import os

from azure.monitor.opentelemetry import configure_azure_monitor
from dotenv import load_dotenv

load_dotenv()
configure_azure_monitor(
    logger_name="gh-webhook"
)
logger = logging.getLogger("gh-webhook")

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
    if event == "workflow_run":
        # https://docs.github.com/en/webhooks/webhook-events-and-payloads?actionType=in_progress#workflow_run
        id = body_json.get("workflow_run", {}).get("id")
        action = body_json.get("action")
        run_event = body_json.get("workflow_run", {}).get("event")
        name = body_json.get("workflow_run", {}).get("name")
        conclusion = body_json.get("workflow_run", {}).get("conclusion")
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
        logger.info(f"Workflow job {id} {action}",
                    extra={
                        "microsoft.custom_event.name": "webhook",
                        "event": event,
                        "job_id": id,
                        "action": action,
                        "run_id": run_id,
                        "runner_id": runner_id,
                        "conclusion": conclusion or "",
                        "run_attempt": run_attempt,
                        "job_name": name
        })
    else:
        # unknown event
        logger.warning(f"Unknown event type: {event}. Payload: {body_json}")


    return func.HttpResponse("Webhook received", status_code=200)
