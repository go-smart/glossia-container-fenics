FROM gosmart/goosefoot-mesher-base

RUN apt-get update && \
    apt-get -qqy install python3-pip libyaml-dev python-yaml python-pip git

###### FROM [jhale/docker]/docker/dockerfiles/stable-ppa/Dockerfile

# Install add-apt-repository
RUN apt-get -qq update && \
    apt-get -qqy install python-software-properties

RUN add-apt-repository -y ppa:fenics-packages/fenics && \
    apt-get -qq update

RUN apt-get -qqy install xauth fenics ipython xterm libopenblas-dev

#PTW: rejoin
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set up user so that we do not run as root
#RUN useradd -m -s /bin/bash -G sudo,docker_env fenics && \
#    echo "fenics:docker" | chpasswd && \
#    echo "fenics ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# See https://github.com/phusion/baseimage-docker/issues/186
#RUN touch /etc/service/syslog-forwarder/down

# OpenBLAS threads should be 1 to ensure performance
RUN echo "export OPENBLAS_NUM_THREADS=1" >> $HOME/.bashrc && \
    echo "export OPENBLAS_VERBOSE=0" >> $HOME/.bashrc

# This makes sure we launch with ENTRYPOINT /bin/bash into the home directory
#ENV HOME /home/fenics
#ADD WELCOME /home/fenics/WELCOME
#RUN cp /home/fenics/.bashrc /home/fenics/.bashrc.tmp && \
#    echo "cd $HOME" >> /home/fenics/.bashrc.tmp && \
#    echo "cat $HOME/WELCOME" >> /home/fenics/.bashrc.tmp

###### END UPSTREAM

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV OPENBLAS_NUM_THREADS=1
ENV OPENBLAS_VERBOSE=0

RUN pip3 install hachiko

ENV GSSA_CONTAINER_MODULE_COMMIT=105713
# Need this for FEniCS
RUN pip2 install git+https://github.com/go-smart/gssa-container-module@$GSSA_CONTAINER_MODULE_COMMIT
# Need this for gosling
RUN pip3 install git+https://github.com/go-smart/gssa-container-module@$GSSA_CONTAINER_MODULE_COMMIT

COPY mesh_and_go.py /

RUN mkdir /var/run/gssf
RUN chown -R gssf /var/run/gssf

USER gssf
ENTRYPOINT ["/usr/local/bin/gosling"]

CMD ["--interpreter", "python3 /mesh_and_go.py", "--archive", "start.tar.gz", "--target", "start.py"]
