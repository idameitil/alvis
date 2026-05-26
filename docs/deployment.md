# Deployment Guide

This document describes how Alvis is deployed to production at **alvis.idameitil.dk** on an Azure Ubuntu VM, and how to replicate the setup on a new server.

## Architecture

```
Internet
   │
   ▼
[VM: 80 / 443]   nginx               (host, public ingress, TLS)
   │
   ▼  proxy_pass → 127.0.0.1:8000
   │
[Docker]   Gunicorn  (1 worker × 3 threads)  →  Flask app
```

- **nginx** runs directly on the VM. It owns ports 80/443, terminates TLS, and reverse-proxies to the container.
- **Gunicorn + Flask** run inside a Docker container. The container's port 8000 is published to `127.0.0.1:8000` only — it is not reachable from the public internet, so all traffic must go through nginx.
- The container is managed by **Docker Compose**, with config in [`deployment/docker-compose.prod.yml`](../deployment/docker-compose.prod.yml).
- Deploys are triggered by pushes to `main` via [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml), which SSHes into the VM, pulls latest, and runs [`deployment/deploy.sh`](../deployment/deploy.sh). The script is the single source of truth for the build + restart + prune steps — both CI and humans run the same thing.

## VM provisioning

### 1. Create the VM

Any Ubuntu 22.04+ VM with at least 2 GB RAM works. Provision an SSH key for access.

### 2. Open inbound ports

In Azure Portal → your VM → Networking → Inbound port rules:

- Port **22** (SSH) — restrict to your IP
- Port **80** (HTTP) — Source: Any
- Port **443** (HTTPS) — Source: Any

### 3. SSH in and create a deploy user

```bash
ssh -i /path/to/key.pem azureuser@<vm-ip>
sudo adduser deploy
sudo usermod -aG sudo deploy
sudo mkdir -p /home/deploy/.ssh
sudo cp ~/.ssh/authorized_keys /home/deploy/.ssh/
sudo chown -R deploy:deploy /home/deploy/.ssh
```

(All subsequent commands assume you've SSH'd in as `deploy`.)

## Install Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker deploy
# log out and back in for the group change to apply
```

Verify:

```bash
docker compose version   # must show v2.x
```

## Clone the repo

```bash
cd ~
git clone https://github.com/idameitil/alvis.git
cd alvis
```

## Install nginx and place the site config

```bash
sudo apt install -y nginx
sudo cp ~/alvis/deployment/nginx/alvis.conf /etc/nginx/sites-available/alvis
sudo ln -s /etc/nginx/sites-available/alvis /etc/nginx/sites-enabled/alvis
sudo rm /etc/nginx/sites-enabled/default   # remove the default welcome page
sudo nginx -t
sudo systemctl reload nginx
```

If you're deploying to a different domain, edit `server_name` in `/etc/nginx/sites-available/alvis` before reloading.

## DNS

Point an A record for your domain (e.g. `alvis.idameitil.dk`) at the VM's public IP. Wait for propagation — verify with `dig +short alvis.idameitil.dk`.

## HTTPS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d alvis.idameitil.dk
```

Certbot rewrites `/etc/nginx/sites-available/alvis` to add a `listen 443 ssl` block, the certificate paths, and an HTTP-to-HTTPS redirect. It also installs a renewal cron.

## Initial deploy

```bash
cd ~/alvis
bash deployment/deploy.sh
```

Verify:

```bash
docker compose -f deployment/docker-compose.prod.yml ps     # container "alvis" Up
curl -I http://127.0.0.1:8000                                # 200 from container
curl -I https://alvis.idameitil.dk                           # 200 through nginx
```

## GitHub Actions auto-deploy

`.github/workflows/deploy.yml` runs on every push to `main`. It SSHes into the VM and runs:

```
cd ~/alvis
git pull origin main
bash deployment/deploy.sh
```

The script (`deployment/deploy.sh`) handles the build, restart, and image prune. Keeping it in the repo means a manual redeploy on the VM runs exactly the same commands as the auto-deploy.

Required repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `VM_HOST` | VM public IP or hostname |
| `VM_USER` | `deploy` |
| `SSH_PRIVATE_KEY` | Private key matching the public key in `~deploy/.ssh/authorized_keys` on the VM |

## Maintenance

### Logs

```bash
# Application (Gunicorn inside the container)
docker compose -f ~/alvis/deployment/docker-compose.prod.yml logs -f

# nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Restart

```bash
# After manual code change
cd ~/alvis
bash deployment/deploy.sh

# After nginx config change
sudo nginx -t && sudo systemctl reload nginx
```

### Free disk

`up -d --build` produces dangling images over time. `deploy.sh` already runs `docker image prune -f` at the end of every deploy. To prune on demand outside a deploy:

```bash
docker image prune -f
```