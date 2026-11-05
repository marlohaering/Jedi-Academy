# Jedi Academy browser MP server: OpenJK dedicated server + password-protected web gateway.
# Build context: web/  (needs web/dist-mp built by build-mp.sh)
#   podman build -f server/Dockerfile -t jka-mp .
FROM docker.io/library/ubuntu:24.04 AS builder
RUN apt-get -q update && DEBIAN_FRONTEND=noninteractive apt-get -q install -y --no-install-recommends \
      build-essential cmake git ca-certificates zlib1g-dev libpng-dev libjpeg-dev && rm -rf /var/lib/apt/lists/*
ARG OPENJK_REF=260c59c
RUN git clone https://github.com/JACoders/OpenJK.git /src && cd /src && git checkout $OPENJK_REF
RUN mkdir /src/build && cd /src/build && cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt \
      -DBuildMPCGame=OFF -DBuildMPEngine=OFF -DBuildMPRdVanilla=OFF -DBuildMPUI=OFF -DBuildMPRend2=OFF \
      -DBuildSPEngine=OFF -DBuildSPGame=OFF -DBuildSPRdVanilla=OFF .. && make -j$(nproc) && make install

FROM docker.io/library/ubuntu:24.04
RUN apt-get -q update && DEBIAN_FRONTEND=noninteractive apt-get -q install -y --no-install-recommends \
      python3 python3-aiohttp zlib1g libstdc++6 tini && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/JediAcademy /opt/openjk
COPY server/gateway.py server/repack.py server/start.sh /opt/gateway/
COPY server/server.cfg /opt/openjk/base/server.cfg
COPY dist-mp/ /opt/web/
RUN chmod +x /opt/gateway/start.sh /opt/openjk/openjkded.x86_64
ENV WEB_DIR=/opt/web DATA_DIR=/data/base GAME_HOST=127.0.0.1 GAME_PORT=29070 PORT=8080
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/gateway/start.sh"]
