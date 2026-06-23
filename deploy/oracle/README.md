# Oracle Deployment Helpers

## 1. systemd service

```bash
cd ~/app
sudo cp deploy/oracle/sales-intelligence.service /etc/systemd/system/sales-intelligence.service
sudo systemctl daemon-reload
sudo systemctl enable sales-intelligence
sudo systemctl restart sales-intelligence
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

Optional cron-based auto update every 10 minutes:

```bash
(crontab -l 2>/dev/null; echo "*/10 * * * * cd /home/ubuntu/app && bash deploy/oracle/update_app.sh >> /home/ubuntu/update_app.log 2>&1") | crontab -
```

Manual updates are safer than cron if the app is used during business hours.
