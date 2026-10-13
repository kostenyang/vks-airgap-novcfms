#!/usr/bin/env bash
# Air-gap 安裝 Docker(靜態二進位,不用 apt / 不連網)
#   用法:install-docker-static.sh /root/staging/docker-29.9.0.tgz [/root/staging/docker-compose-linux-x86_64]
set -euo pipefail
TGZ=${1:?docker-*.tgz}
COMPOSE=${2:-}

tar -xzf "$TGZ" -C /tmp
install -m 0755 /tmp/docker/* /usr/bin/
rm -rf /tmp/docker
getent group docker >/dev/null || groupadd docker

cat >/etc/systemd/system/containerd.service <<'EOF'
[Unit]
Description=containerd container runtime
After=network.target local-fs.target
[Service]
ExecStartPre=-/sbin/modprobe overlay
ExecStart=/usr/bin/containerd
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
OOMScoreAdjust=-999
[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/docker.socket <<'EOF'
[Unit]
Description=Docker Socket for the API
[Socket]
ListenStream=/run/docker.sock
SocketMode=0660
SocketUser=root
SocketGroup=docker
[Install]
WantedBy=sockets.target
EOF

cat >/etc/systemd/system/docker.service <<'EOF'
[Unit]
Description=Docker Application Container Engine
After=network-online.target docker.socket containerd.service
Wants=network-online.target containerd.service
Requires=docker.socket
[Service]
Type=notify
ExecStart=/usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
ExecReload=/bin/kill -s HUP $MAINPID
TimeoutStartSec=0
RestartSec=2
Restart=always
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
Delegate=yes
KillMode=process
OOMScoreAdjust=-500
[Install]
WantedBy=multi-user.target
EOF

if [ -n "$COMPOSE" ]; then
  install -D -m 0755 "$COMPOSE" /usr/local/lib/docker/cli-plugins/docker-compose
fi

systemctl daemon-reload
systemctl enable --now containerd docker.socket docker
docker version --format 'docker client {{.Client.Version}} / server {{.Server.Version}}'
[ -n "$COMPOSE" ] && docker compose version || true
