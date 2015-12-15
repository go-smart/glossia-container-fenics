FROM fenicsproject/stable-ppa:master

RUN apt-get update && \
    apt-get -qqy install python3-pip libyaml-dev python-yaml python-pip git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN pip3 install hachiko

COPY init.sh /

ENV GSSA_CONTAINER_MODULE_COMMIT=612c347a8f9d1f95d14e802344361e1df8dd009d
RUN pip install git+https://github.com/numa-engineering/gosmart-gssa_container-module@$GSSA_CONTAINER_MODULE_COMMIT
