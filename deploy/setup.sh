#!/bin/bash
# crew-bus Hetzner deployment setup
# Run as root on a fresh Ubuntu 22.04+ server
# Usage: bash setup.sh

set -euo pipefail

DOMAIN="crew-bus.dev"
APP_DIR="/opt/crew-bus"
USER="crewbus"

echo "=== crew-bus deployment setup ==="

# 1. System updates
echo "[1/8] Updating system..."
apt-get update && apt-get upgrade -y

# 2. Install dependencies
echo "[2/8] Installing dependencies..."
apt-get install -y nginx certbot python3-certbot-nginx python3-venv python3-pip ufw git

# 3. Create app user
echo "[3/8] Creating app user..."
if ! id "$USER" &>/dev/null; then
    useradd -r -m -s /bin/bash "$USER"
fi

# 4. Clone/update app
echo "[4/8] Setting up application..."
if [ ! -d "$APP_DIR" ]; then
    git clone https://github.com/crew-bus/crew-bus.git "$APP_DIR"
else
    cd "$APP_DIR" && git pull
fi
chown -R "$USER:$USER" "$APP_DIR"

# 5. Python virtual environment
echo "[5/8] Setting up Python environment..."
cd "$APP_DIR"
sudo -u "$USER" python3 -m venv venv
sudo -u "$USER" venv/bin/pip install -r requirements.txt
sudo -u "$USER" venv/bin/pip install stripe

# 6. Environment file
if [ ! -f "$APP_DIR/.env" ]; then
    echo "[5.5/8] Creating .env template..."
    cat > "$APP_DIR/.env" << 'ENVEOF'
STRIPE_SECRET_KEY=sk_live_REPLACE_ME
STRIPE_WEBHOOK_SECRET=whsec_REPLACE_ME
STRIPE_GUARD_PRICE_ID=
SITE_URL=https://crew-bus.dev
ENVEOF
    chown "$USER:$USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo "  >> Edit /opt/crew-bus/.env with your Stripe keys!"
fi

# 7. Firewall
echo "[6/8] Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 8. Nginx
echo "[7/8] Configuring Nginx..."
cp "$APP_DIR/deploy/nginx.conf" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 9. SSL
echo "[8/8] Setting up SSL..."
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" || {
    echo "  >> Certbot failed — run manually: certbot --nginx -d $DOMAIN"
}

# 10. Systemd service
echo "[+] Installing systemd service..."
mkdir -p /var/log/crew-bus
chown "$USER:$USER" /var/log/crew-bus
cp "$APP_DIR/deploy/crew-bus.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable crew-bus
systemctl start crew-bus

# 11. Log rotation
cat > /etc/logrotate.d/crew-bus << 'LOGEOF'
/var/log/crew-bus/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        systemctl restart crew-bus
    endscript
}
LOGEOF

echo ""
echo "=== Setup complete ==="
echo "  Site:     https://$DOMAIN"
echo "  App:      $APP_DIR"
echo "  Service:  systemctl status crew-bus"
echo "  Logs:     journalctl -u crew-bus -f"
echo "  .env:     $APP_DIR/.env (edit Stripe keys!)"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/crew-bus/.env with your Stripe keys"
echo "  2. Create Stripe product for Guard ($20)"
echo "  3. Set up Stripe webhook endpoint: https://$DOMAIN/api/stripe/webhook"
echo "  4. Verify DNS A record points to this server"
echo ""
