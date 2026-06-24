FROM public.ecr.aws/sam/build-python3.12:latest-x86_64 AS base

# Poetry envvars
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_NO_INTERACTION=1
ENV PYSETUP_PATH="/var/task"
ENV VENV_PATH="/var/task/.venv"

ENV LD_LIBRARY_PATH=/lib:/usr/lib:/usr/local/lib
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"
ENV PATH=/root/.local/bin:/sbin:/usr/sbin:${PATH}

RUN dnf upgrade -y
RUN dnf group install -y "Development Tools"
RUN dnf install -y gcc git libcurl-devel make openssl openssl-devel which

RUN git clone https://github.com/confluentinc/librdkafka  && \
    cd librdkafka && git checkout tags/v2.6.0 && \
    ./configure --install-deps && make && make install && \
    ldconfig

# Generate self-signed cert
RUN mkdir /etc/ssl/transaction \
    && openssl genrsa -out /etc/ssl/transaction/server.key 2048 \
    && openssl req -new -key /etc/ssl/transaction/server.key -out /etc/ssl/transaction/server.csr \
        -subj '/C=/ST=/L=/O=esgf-west.org/OU=discovery-api/CN=uvicorn' \
    && openssl x509 -req -days 365 -in /etc/ssl/transaction/server.csr \
        -signkey /etc/ssl/transaction/server.key -out /etc/ssl/transaction/server.crt


FROM base AS builder

# Install poetry
RUN pip install poetry

WORKDIR $PYSETUP_PATH

ENV PATH="$POETRY_HOME/bin:$PATH"

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --with globus

FROM base AS production

COPY --from=builder $VENV_PATH $VENV_PATH
ENV PATH="/var/task/.venv/bin:$PATH"

WORKDIR /var/task
COPY ./src .

CMD ["uvicorn", "api:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--forwarded-allow-ips", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16", \
     "--ssl-keyfile", "/etc/ssl/transaction/server.key", \
     "--ssl-certfile", "/etc/ssl/transaction/server.crt"]
