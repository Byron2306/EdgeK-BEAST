FROM python:3.11-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git \
        openssh-server \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /run/sshd /root/.ssh \
    && chmod 700 /root/.ssh \
    && echo 'root:discarded-test-password' | chpasswd \
    && git config --global --add safe.directory '*' \
    && printf '%s\n' \
        'PermitRootLogin yes' \
        'PubkeyAuthentication yes' \
        'PasswordAuthentication no' \
        'UsePAM no' \
        'KbdInteractiveAuthentication no' \
        'ChallengeResponseAuthentication no' \
        'AuthorizedKeysFile .ssh/authorized_keys' \
        >> /etc/ssh/sshd_config

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D", "-e"]
