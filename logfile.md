# Deployment Guide — Azure Ubuntu VM

## What they are and why you need them

**Flask's dev server** (`python app.py`) is single-threaded and not designed for production. It can only handle one request at a time and crashes easily.

**Gunicorn** is a production WSGI server that:
- Runs multiple worker processes (handles concurrent requests)
- Automatically restarts workers if they crash
- Pre-forks workers for better performance
- Manages worker lifecycle

**Nginx** is a reverse proxy that sits in front of gunicorn:
- Handles SSL/TLS termination (HTTPS)
- Serves static files directly (faster than Python)
- Buffers slow clients (gunicorn workers stay free)
- Load balances across multiple gunicorn instances
- Protects against common attacks (rate limiting, request size limits)

**The flow:** `Browser → Nginx (port 80/443) → Gunicorn (localhost:8000) → Flask app`

---

## Initial Setup

### 1. Copy files to server

```bash
rsync -avz -e "ssh -i /path/to/your/private-key.pem" \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'temp_*' \
  /Users/idameitil/alvis/ \
  user@your-vm-ip:/home/user/alvis/
```

### 2. Azure Network Security Group

In Azure Portal → your VM → Networking → Inbound port rules:
- Add rule allowing port 80: Source: Any, Destination port: 80, Protocol: TCP, Action: Allow
- Add rule allowing port 443 (if using HTTPS later): Destination port: 443, Protocol: TCP

### 3. SSH into server and set up Python environment

```bash
ssh -i /path/to/key.pem user@your-vm-ip
cd alvis
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Production Setup with Gunicorn + Nginx

### 1. Install dependencies

```bash
sudo apt update
sudo apt install -y nginx python3-pip
pip install gunicorn
```

### 2. Create systemd service for gunicorn

```bash
sudo nano /etc/systemd/system/alvis.service
```

Paste (replace `YOUR_USERNAME` with your actual username):

```ini
[Unit]
Description=Alvis Gunicorn Service
After=network.target

[Service]
User=YOUR_USERNAME
Group=www-data
WorkingDirectory=/home/YOUR_USERNAME/alvis
Environment="PATH=/home/YOUR_USERNAME/alvis/venv/bin"
ExecStart=/home/YOUR_USERNAME/alvis/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 app:app

[Install]
WantedBy=multi-user.target
```

**--workers 3** means 3 concurrent worker processes (rule of thumb: `2 * num_cpus + 1`)

### 3. Start gunicorn

```bash
sudo systemctl daemon-reload
sudo systemctl start alvis
sudo systemctl enable alvis  # start on boot
sudo systemctl status alvis  # check it's running
```

### 4. Configure nginx

```bash
sudo nano /etc/nginx/sites-available/alvis
```

Paste (replace `YOUR_VM_IP_OR_DOMAIN` and `YOUR_USERNAME`):

```nginx
server {
    listen 80;
    server_name YOUR_VM_IP_OR_DOMAIN;

    client_max_body_size 50M;  # Allow large ZIP/PDB uploads

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long-running DSSP analysis
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }

    location /static {
        alias /home/YOUR_USERNAME/alvis/static;
        expires 30d;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/alvis /etc/nginx/sites-enabled/
sudo nginx -t  # test config
sudo systemctl restart nginx
```

---

## Why this is resilient

1. **Gunicorn workers**: If one crashes during DSSP parsing, others keep serving requests
2. **Auto-restart**: Systemd restarts gunicorn if it fully crashes
3. **Nginx buffering**: Slow clients don't tie up gunicorn workers
4. **Proper timeouts**: Long-running requests don't hang forever
5. **Static file serving**: Nginx serves CSS/JS directly (doesn't touch Python)

---

## Maintenance

### View logs

```bash
# Gunicorn logs
sudo journalctl -u alvis -f

# Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Restart services

```bash
# After code changes
sudo systemctl restart alvis

# After nginx config changes
sudo nginx -t && sudo systemctl reload nginx
```

### Update code

```bash
# On your local machine
rsync -avz -e "ssh -i /path/to/key.pem" \
  --exclude 'venv' --exclude '__pycache__' --exclude '.git' \
  /Users/idameitil/alvis/ user@your-vm-ip:/home/user/alvis/

# On the server
sudo systemctl restart alvis
```

---

## Optional: HTTPS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Certbot will automatically modify your nginx config and set up auto-renewal.
