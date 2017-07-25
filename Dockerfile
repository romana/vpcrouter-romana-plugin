FROM bitnami/minideb
ADD requirements/deploy.txt /tmp/requirements.txt 
ADD . /code
WORKDIR /code
RUN apt-get update && \
    apt-get install -y wget g++ libc-dev python-dev python-setuptools && \
    apt-mark manual python-minimal python-pkg-resources python2.7 python2.7-minimal && \
    python setup.py install && \
    apt-get purge -y wget g++ libc-dev python-dev python-setuptools && \
    apt-get -y autoremove && \
    rm -rf /var/log/* /var/cache/* /var/lib/apt/* /var/dpkg/* && \
    rm -rf /usr/share/man/* /usr/share/info/* /usr/share/lintian/* \
           /usr/share/doc/* /usr/share/bash-completions/*
ENTRYPOINT ["vpcrouter", "-l", "-", "-m", "vpcrouter_romana_plugin.romana"]
