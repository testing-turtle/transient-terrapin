#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive
export TZ=America/New_York

apt-get update
apt-get install -y openssh-server
mkdir -p /var/run/sshd

echo "PermitRootLogin yes" | tee -a /etc/ssh/sshd_config
echo "PasswordAuthentication no" | tee -a /etc/ssh/sshd_config
echo "PubkeyAuthentication yes" | tee -a /etc/ssh/sshd_config
echo "Port 2200" | tee -a /etc/ssh/sshd_config
echo "ListenAddress 0.0.0.0" | tee -a /etc/ssh/sshd_config

mkdir -p ~/.ssh
chmod 0700 ~/.ssh
cat gh-ssh.key.pub >> ~/.ssh/authorized_keys


service ssh start
