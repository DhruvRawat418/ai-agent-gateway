# Deployment operations

## Verified state and operational follow-ups

The operator verified the Docker image on EC2, staff authentication against Neon, a live two-request budget trial, HTTPS at https://dhruvaigateway.duckdns.org, and removal of public TCP 8000 access. On November 6, 2026 (November 7 UTC), the operator also confirmed that the DuckDNS timer was enabled and active, with successful update logs. A new Mac SSH connection succeeded after updating its allowed IP. The final security-group rules and fresh browser SSH access have not been independently audited. No AWS credentials or DNS tokens are included in this repository.

Containers: `my-live-gateway` (image `ai-gateway:dashboard-v1`), `gateway-caddy` (Caddy 2, host networking). Both use `unless-stopped`. The gateway reads `/home/ubuntu/gateway/.env` through a read-only mount at `/app/.env`. Caddy reads `/home/ubuntu/gateway-caddy/Caddyfile` and retains certificates in Docker volumes `gateway-caddy-data` and `gateway-caddy-config`. Keep those volumes when replacing Caddy.

The old container `gateway-before-dashboard` is a rollback artifact. The private preview `gateway-dashboard-preview` may still be running on loopback port 8001. Remove the preview only after confirming the public service works. The old code lacks current safeguards; do not treat reverting to it as a long-term solution.

## 1. Restrict SSH without losing browser access

Keep the current terminal connected while editing the security group. In EC2 → instance → Security → launch-wizard-1 → Edit inbound rules:

1. Add SSH / TCP 22 with Source **My IP**. This should be your current public IPv4 followed by `/32`, allowing your Mac on this network.
2. Add SSH / TCP 22 with Source **Custom**, then select AWS-managed prefix list `com.amazonaws.us-east-2.ec2-instance-connect` (IPv4, matching the instance's region). This preserves browser-based EC2 Instance Connect; do not choose the IPv6 list.
3. Save. Then remove the old SSH rule from `0.0.0.0/0`; also remove an unrestricted SSH `::/0` rule if one exists. Keep both scoped SSH rules, public TCP 80 and 443, and no public TCP 8000 rule.
4. Save and test a **new** Mac SSH connection and a **new** EC2 browser connection before closing the existing session. Existing sessions alone do not prove that new access works.

Mac check (use the downloaded private key locally, never upload it):

```bash
ssh -i "$HOME/Downloads/gateway-key.pem" ubuntu@dhruvaigateway.duckdns.org
```

If your Mac changes network/public IP, update the My IP rule through AWS. Browser access remains available through the regional prefix list. If the prefix list is not offered, stop and check the selected AWS region rather than substituting an arbitrary CIDR.

Source: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-connect-prerequisites.html

## 2. Keep DuckDNS aligned with the EC2 public IP

The host-side updater uses an IMDSv2 token to read `public-ipv4`, validates the address, and sends it to DuckDNS over HTTPS. It runs 30 seconds after boot and every five minutes thereafter. It does not require an AWS IAM role and does not query OpenAI. Its token is kept in a root-owned file with mode 600, not in Docker images, shell history, or command arguments. Failures omit token-bearing URLs and return a nonzero exit status.

From the repository root on your Mac, create and upload an operations bundle. These commands target the current deployment; adapt the host, username, key path, and installer domain for another deployment:

```bash
tar -czf /tmp/gateway-ops-docs.tar.gz ops docs README.md DASHBOARD.md
scp -i "$HOME/Downloads/gateway-key.pem" \
  /tmp/gateway-ops-docs.tar.gz \
  ubuntu@dhruvaigateway.duckdns.org:/home/ubuntu/gateway-ops-docs.tar.gz
```

Then in the **EC2 terminal**:

```bash
mkdir -p /home/ubuntu/gateway-ops
tar -xzf /home/ubuntu/gateway-ops-docs.tar.gz -C /home/ubuntu/gateway-ops
cd /home/ubuntu/gateway-ops
sudo bash ops/install-duckdns.sh
```

At the hidden prompt, paste the account token from your DuckDNS dashboard. It is not the gateway admin key or the OpenAI key. Do not send the token in chat. The installer retains existing configuration on repeated runs. It starts the updater once and enables the timer only after success.

Verify:

```bash
sudo systemctl list-timers gateway-duckdns.timer --no-pager
sudo journalctl -u gateway-duckdns.service -n 10 --no-pager
getent ahostsv4 dhruvaigateway.duckdns.org
curl -sS -o /dev/null -w 'HTTPS status: %{http_code}\n' https://dhruvaigateway.duckdns.org/docs
```

Expected: scheduled timer, `DuckDNS update accepted for public IPv4 ...`, DNS matching EC2, HTTPS 200. `systemctl status gateway-duckdns.service` can show inactive (dead) after a successful one-shot run; the timer should be active.

Do not stop/start the live instance just to test IP changes. The timer reduces manual work, but DNS caching means some interruption remains possible after a stop/start. This is not high availability. An instance with no public IP cannot be fixed by this updater. Keep its DNS record's IPv6 field empty unless IPv6 is deliberately configured.

To disable updates without changing the current DNS record:

```bash
sudo systemctl disable --now gateway-duckdns.timer
```

For token rotation, privately edit `/etc/gateway-duckdns.json` with `sudoedit`, retain mode 600, and rerun the service. Failed requests retry at the next timer interval; there is no external alerting yet.

Sources: https://www.duckdns.org/spec.jsp and https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html

## 3. Deployment checks and limits

Fresh databases require `python -c 'from database import init_db; init_db()'` before serving traffic. Current startup creates cost/attempt tables but does not bootstrap all tables on an empty database. Never substitute a development database URL into the live environment by accident.

Review dependencies and run the suite before rebuilding images. For the current deployment, requirements were resolved at build time; image tags and dependency versions are not a reproducible release lock. Follow-up work should pin dependencies, record image digests, and automate checks.

Do not publish real staff or department keys in a README, recording, screenshot, or public demo. A hosted admin login page is not a read-only recruiter sandbox. Local development and production should use separate Neon branches/databases.

Host updates/reboots, backup restore drills, credential hashing/rotation, and provider-charge reconciliation remain operational follow-ups. A Docker restart policy does not by itself prove reboot recovery; confirm Docker is enabled at boot before scheduling maintenance. Do not prune certificate volumes or remove the rollback image during routine cleanup.
