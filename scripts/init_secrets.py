"""Generate a private, unguessable ntfy topic. Store it as the GitHub secret NTFY_TOPIC (never in the repo)."""
import secrets

print("NTFY_TOPIC=mb-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "").lower())
