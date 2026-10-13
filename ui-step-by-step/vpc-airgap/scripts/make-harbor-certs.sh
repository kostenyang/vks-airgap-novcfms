#!/usr/bin/env bash
# 自簽 CA + Harbor 伺服器憑證(air-gap 內部用)
#   用法:make-harbor-certs.sh harbor01.home.lab 10.0.0.86 /data/cert
set -euo pipefail
FQDN=${1:?fqdn}; IP=${2:?ip}; DIR=${3:-/data/cert}
mkdir -p "$DIR" && cd "$DIR"

# 1) 內部 CA(10 年)
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -sha512 -days 3650 -key ca.key -out ca.crt \
  -subj "/C=TW/O=home.lab/OU=airgap-lab/CN=airgap-lab Root CA"

# 2) Harbor 伺服器憑證(SAN = FQDN + 短名 + IP)
openssl genrsa -out "$FQDN.key" 4096
openssl req -new -sha512 -key "$FQDN.key" -out "$FQDN.csr" -subj "/C=TW/O=home.lab/OU=airgap-lab/CN=$FQDN"
cat > v3.ext <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$FQDN,DNS:${FQDN%%.*},IP:$IP
EOF
openssl x509 -req -sha512 -days 825 -extfile v3.ext -CA ca.crt -CAkey ca.key -CAcreateserial -in "$FQDN.csr" -out "$FQDN.crt"

# 3) docker 用戶端信任(本機 push/pull 用)
mkdir -p "/etc/docker/certs.d/$FQDN"
cp ca.crt "/etc/docker/certs.d/$FQDN/ca.crt"

chmod 600 ca.key "$FQDN.key"
openssl x509 -in "$FQDN.crt" -noout -subject -issuer -ext subjectAltName -enddate
