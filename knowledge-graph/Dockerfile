FROM pgvector/pgvector:pg16

# Build Apache AGE from source
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libreadline-dev \
        zlib1g-dev \
        flex \
        bison \
        postgresql-server-dev-16 \
    && cd /tmp \
    && GIT_SSL_NO_VERIFY=1 git clone --branch release/PG16/1.5.0 https://github.com/apache/age.git \
    && cd /tmp/age \
    && make && make install \
    && cd / && rm -rf /tmp/age \
    && apt-get purge -y build-essential git libreadline-dev zlib1g-dev flex bison postgresql-server-dev-16 \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
