import hashlib
import hmac


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