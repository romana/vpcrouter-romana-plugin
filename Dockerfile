FROM nimmis/alpine-python:2
ADD requirements/deploy.txt /tmp/requirements.txt 
ADD . /code
WORKDIR /code
RUN apk add --no-cache --update alpine-sdk
RUN apk add --no-cache --update python-dev
RUN python setup.py install
RUN apk del python-dev
RUN apk del alpine-sdk
ENTRYPOINT ["vpcrouter", "-l", "-", "-m", "vpcrouter_romana_plugin.romana"]
