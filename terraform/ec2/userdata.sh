#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/userdata.log) 2>&1
echo "=== Finly EC2 Setup: $(date) ==="

AWS_REGION="${aws_region}"
ECR_REGISTRY="${ecr_registry}"
BACKEND_IMAGE="${backend_ecr_url}:latest"
AGENT_IMAGE="${agent_ecr_url}:latest"

# ── 시스템 업데이트 & 패키지 설치 ─────────────────────────
dnf update -y
dnf install -y docker nginx

systemctl enable --now docker
usermod -aG docker ec2-user

# Docker Compose 플러그인
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ── nginx 설정 ────────────────────────────────────────────
cat > /etc/nginx/conf.d/finly.conf << 'NGINXEOF'
server {
    listen 80;

    location /api/ {
        rewrite ^/api/(.*)$ /$1 break;
        proxy_pass         http://localhost:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }

    location /agent/ {
        rewrite ^/agent/(.*)$ /$1 break;
        proxy_pass         http://localhost:8001;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }
}
NGINXEOF

systemctl enable --now nginx

# ── SSM에서 시크릿 로드 ───────────────────────────────────
get_param() {
  aws ssm get-parameter --name "$1" --with-decryption \
    --region "$AWS_REGION" --query Parameter.Value --output text
}

DB_PASSWORD=$(get_param "/finly/DB_PASSWORD")
CLAUDE_API_KEY=$(get_param "/finly/CLAUDE_API_KEY")
ALPACA_API_KEY=$(get_param "/finly/ALPACA_API_KEY")
ALPACA_API_SECRET=$(get_param "/finly/ALPACA_API_SECRET")
JWT_SECRET=$(get_param "/finly/JWT_SECRET")
ADMIN_USERNAME=$(get_param "/finly/ADMIN_USERNAME")
ADMIN_PASSWORD_HASH=$(get_param "/finly/ADMIN_PASSWORD_HASH")
TOTP_SECRET=$(aws ssm get-parameter --name "/finly/TOTP_SECRET" --with-decryption \
  --region "$AWS_REGION" --query Parameter.Value --output text 2>/dev/null || echo "")

# ── Docker Compose 설정 ───────────────────────────────────
mkdir -p /opt/finly

aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# $DB_PASSWORD 등 bash 변수는 런타임에 확장, ${frontend_origin}은 Terraform이 미리 치환
cat > /opt/finly/docker-compose.yml << EOF
version: '3.8'
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=finly
      - POSTGRES_PASSWORD=$DB_PASSWORD
      - POSTGRES_DB=finly
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finly"]
      interval: 10s
      timeout: 5s
      retries: 5

  finly-backend:
    image: $BACKEND_IMAGE
    restart: unless-stopped
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://finly:$DB_PASSWORD@postgres:5432/finly
      - FRONTEND_ORIGIN=${frontend_origin}
      - CLAUDE_API_KEY=$CLAUDE_API_KEY
      - ALPACA_API_KEY=$ALPACA_API_KEY
      - ALPACA_API_SECRET=$ALPACA_API_SECRET
      - JWT_SECRET=$JWT_SECRET
      - ADMIN_USERNAME=$ADMIN_USERNAME
      - ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH
      - TOTP_SECRET=$TOTP_SECRET

  finly-agent:
    image: $AGENT_IMAGE
    restart: unless-stopped
    ports:
      - "8001:8001"
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://finly:$DB_PASSWORD@postgres:5432/finly
      - CLAUDE_API_KEY=$CLAUDE_API_KEY
      - ALPACA_API_KEY=$ALPACA_API_KEY
      - ALPACA_API_SECRET=$ALPACA_API_SECRET

volumes:
  pgdata:
EOF

# ── systemd 서비스 ─────────────────────────────────────────
cat > /etc/systemd/system/finly.service << 'SERVICEEOF'
[Unit]
Description=Finly Application
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/finly
ExecStart=/usr/local/lib/docker/cli-plugins/docker-compose up -d --pull always
ExecStop=/usr/local/lib/docker/cli-plugins/docker-compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable finly

# 최초 배포 시 ECR 이미지가 없을 수 있으므로 실패해도 계속 진행
docker-compose -f /opt/finly/docker-compose.yml up -d || \
  echo "이미지 없음 — ECR에 push 후 'systemctl start finly' 실행"

echo "=== Setup complete: $(date) ==="
