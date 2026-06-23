# Oracle Deployment Helpers

## 1. systemd service

```bash
cd ~/app
sudo cp deploy/oracle/sales-intelligence.service /etc/systemd/system/sales-intelligence.service
sudo cp deploy/oracle/sales-mobile.service /etc/systemd/system/sales-mobile.service
sudo cp deploy/oracle/sales-reminder.service /etc/systemd/system/sales-reminder.service
sudo cp deploy/oracle/sales-reminder.timer /etc/systemd/system/sales-reminder.timer
sudo systemctl daemon-reload
sudo systemctl enable sales-intelligence sales-mobile sales-reminder.timer
sudo systemctl restart sales-intelligence
sudo systemctl restart sales-mobile
sudo systemctl restart sales-reminder.timer
sudo systemctl status sales-intelligence --no-pager
```

## 2. Reboot verification

```bash
sudo reboot
```

Reconnect after 1-2 minutes:

```bash
ssh -i "D:\Project\Server Setup_oracle\ssh-key-2026-06-23.key" ubuntu@161.33.148.67
cd ~/app
bash deploy/oracle/healthcheck.sh
```

## 3. Git update automation

```bash
cd ~/app
chmod +x deploy/oracle/*.sh
bash deploy/oracle/update_app.sh
```

The Telegram reminder timer runs every minute and sends due schedule reminders using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `.env` or `.streamlit/secrets.toml`.

Optional cron-based auto update every 10 minutes:

```bash
(crontab -l 2>/dev/null; echo "*/10 * * * * cd /home/ubuntu/app && bash deploy/oracle/update_app.sh >> /home/ubuntu/update_app.log 2>&1") | crontab -
```

Manual updates are safer than cron if the app is used during business hours.

## 4. HTTPS reverse proxy

The Oracle VM is prepared to serve the app through Caddy:

```bash
sudo snap install caddy
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo mkdir -p /var/snap/caddy/common
sudo cp deploy/oracle/Caddyfile /var/snap/caddy/common/Caddyfile
sudo cp deploy/oracle/caddy-proxy.service /etc/systemd/system/caddy-proxy.service
sudo systemctl daemon-reload
sudo systemctl enable caddy-proxy
sudo systemctl restart caddy-proxy
```

Oracle Cloud console must also allow inbound TCP `80` and `443` in the instance subnet/security list.

HTTPS URL:

```text
https://161.33.148.67.sslip.io
```
