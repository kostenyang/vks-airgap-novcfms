#!/bin/bash
# Air-gapped Harbor install on harbor.alan.lab (120.80). Expects ~/airgap/ copied from bastion:
#   docker-debs/*.deb, harbor-offline-installer-<ver>.tgz, SHA256SUMS
# Creates a self-signed CA + server cert (SAN: harbor.alan.lab, 192.168.120.80), installs Harbor over HTTPS (no Trivy).
set -euo pipefail
FQDN=harbor.alan.lab; IP=192.168.120.80; ADMIN_PW="${LAB_PASSWORD:?export LAB_PASSWORD first}"
cd ~/airgap && sed -i "s|/home/ubuntu/airgap/||" SHA256SUMS && sha256sum -c SHA256SUMS
# 1. docker (offline)
if ! command -v docker >/dev/null; then sudo dpkg -i docker-debs/*.deb; fi
sudo systemctl enable --now docker; sudo usermod -aG docker ubuntu
docker --version; docker compose version
# 2. CA + server cert
sudo mkdir -p /data/cert && cd /data/cert
if [ ! -f ca.crt ]; then
  sudo openssl genrsa -out ca.key 4096
  sudo openssl req -x509 -new -nodes -sha512 -days 3650 -subj "/C=TW/O=alan.lab/CN=alan.lab Harbor Root CA" -key ca.key -out ca.crt
  sudo openssl genrsa -out $FQDN.key 4096
  sudo openssl req -sha512 -new -subj "/C=TW/O=alan.lab/CN=$FQDN" -key $FQDN.key -out $FQDN.csr
  printf "authorityKeyIdentifier=keyid,issuer\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:$FQDN,DNS:harbor,IP:$IP\n" | sudo tee v3.ext >/dev/null
  sudo openssl x509 -req -sha512 -days 825 -extfile v3.ext -CA ca.crt -CAkey ca.key -CAcreateserial -in $FQDN.csr -out $FQDN.crt
fi
openssl x509 -in /data/cert/$FQDN.crt -noout -subject -issuer -ext subjectAltName -enddate
# trust CA for docker + system
sudo mkdir -p /etc/docker/certs.d/$FQDN && sudo cp /data/cert/ca.crt /etc/docker/certs.d/$FQDN/ca.crt
sudo cp /data/cert/ca.crt /usr/local/share/ca-certificates/alan-lab-harbor-ca.crt && sudo update-ca-certificates >/dev/null
# 3. harbor
cd ~ && tar xzf ~/airgap/harbor-offline-installer-*.tgz && cd ~/harbor
cp harbor.yml.tmpl harbor.yml
sed -i "s/^hostname: .*/hostname: $FQDN/" harbor.yml
sed -i "s#^  certificate: .*#  certificate: /data/cert/$FQDN.crt#" harbor.yml
sed -i "s#^  private_key: .*#  private_key: /data/cert/$FQDN.key#" harbor.yml
sed -i "s/^harbor_admin_password: .*/harbor_admin_password: $ADMIN_PW/" harbor.yml
grep -E '^hostname|^  (certificate|private_key)|^harbor_admin_password|^data_volume|^  port' harbor.yml | sed 's/\(password: \).*/\1***/'
sudo ./install.sh 2>&1 | tail -15
# 4. verify
sleep 10
curl -fsS https://$FQDN/api/v2.0/health | jq -c '{status: .status, components: [.components[] | {(.name): .status}] | add}'
echo "$ADMIN_PW" | sudo docker login $FQDN -u admin --password-stdin
