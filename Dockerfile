FROM bitnami/minideb
ADD requirements/deploy.txt /tmp/requirements.txt 
ADD . /code
WORKDIR /code
RUN apt-get update && \
    apt-get install -y wget g++ libc-dev python-dev python-setuptools && \
    apt-mark manual python-minimal python-pkg-resources python2.7 python2.7-minimal && \
    python setup.py install && \
    apt-get purge -y wget g++ libc-dev python-dev python-setuptools && \
    apt-get -y autoremove
ENTRYPOINT ["vpcrouter", "-l", "-", "-m", "vpcrouter_romana_plugin.romana"]
