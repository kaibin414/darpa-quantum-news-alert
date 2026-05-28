# DARPA Quantum News Alert

This project checks the official DARPA News RSS feed every hour and sends only quantum-related DARPA news to Discord.

## GitHub Secret

Add this repository secret:

- `DISCORD_WEBHOOK_URL`: your Discord webhook URL

Do not commit the webhook URL into the repository.

## Manual Run

Use the GitHub Actions `workflow_dispatch` button:

- `test_mode=true`: send one Discord test message
- `test_mode=false`: check DARPA news normally
