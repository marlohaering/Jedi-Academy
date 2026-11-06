# Jedi Academy browser MP server: OpenJK dedicated server + password-protected web gateway.
# Build context: web/  (needs web/dist-mp built by build-mp.sh)
#   podman build -f server/Dockerfile -t jka-mp .
# 32-bit (i386) userland: closed-source server mods such as JA+ only exist as jampgamei386.so,
# and a 64-bit openjkded cannot load them.
FROM --platform=linux/386 docker.io/i386/debian:bookworm AS builder
RUN apt-get -q update && DEBIAN_FRONTEND=noninteractive apt-get -q install -y --no-install-recommends \
      build-essential cmake git ca-certificates zlib1g-dev libpng-dev libjpeg-dev && rm -rf /var/lib/apt/lists/*
ARG OPENJK_REF=260c59c
RUN git clone https://github.com/JACoders/OpenJK.git /src && cd /src && git checkout $OPENJK_REF
# uname -m says x86_64 under a 64-bit kernel; setarch makes cmake pick the i386 architecture
RUN mkdir /src/build && cd /src/build && setarch i686 cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt \
      -DBuildMPCGame=OFF -DBuildMPEngine=OFF -DBuildMPRdVanilla=OFF -DBuildMPUI=OFF -DBuildMPRend2=OFF \
      -DBuildSPEngine=OFF -DBuildSPGame=OFF -DBuildSPRdVanilla=OFF .. && make -j$(nproc) && make install

FROM --platform=linux/386 docker.io/i386/debian:bookworm
RUN apt-get -q update && DEBIAN_FRONTEND=noninteractive apt-get -q install -y --no-install-recommends \
      python3 python3-aiohttp zlib1g libstdc++6 tini && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/JediAcademy /opt/openjk
COPY server/gateway.py server/repack.py server/start.sh /opt/gateway/
COPY server/server.cfg /opt/openjk/base/server.cfg
COPY dist-mp/ /opt/web/
RUN chmod +x /opt/gateway/start.sh /opt/openjk/openjkded.i386
ENV WEB_DIR=/opt/web DATA_DIR=/data/base GAME_HOST=127.0.0.1 GAME_PORT=29070 PORT=8080
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/gateway/start.sh"]
