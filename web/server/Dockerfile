# Jedi Academy browser MP server: OpenJK dedicated server + JA++ server mod + password-protected web gateway.
# Build context: web/  (needs web/dist-mp built by build-mp.sh)
#   podman build -f server/Dockerfile -t jka-mp .
FROM docker.io/library/ubuntu:24.04 AS builder
RUN apt-get -q update && DEBIAN_FRONTEND=noninteractive apt-get -q install -y --no-install-recommends \
      build-essential cmake git ca-certificates zlib1g-dev libpng-dev libjpeg-dev scons python3 libreadline-dev \
      && rm -rf /var/lib/apt/lists/*
ARG OPENJK_REF=260c59c
RUN git clone https://github.com/JACoders/OpenJK.git /src && cd /src && git checkout $OPENJK_REF
RUN mkdir /src/build && cd /src/build && cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt \
      -DBuildMPCGame=OFF -DBuildMPEngine=OFF -DBuildMPRdVanilla=OFF -DBuildMPUI=OFF -DBuildMPRend2=OFF \
      -DBuildSPEngine=OFF -DBuildSPGame=OFF -DBuildSPRdVanilla=OFF .. && make -j$(nproc) && make install
# JA++ (github.com/Razish/japp, GPL): only the server-side game module; browser clients keep the
# cgame/ui compiled into openjk_mp.wasm (JA++ supports base clients)
ARG JAPP_REF=6407f98
RUN git clone https://github.com/Razish/japp.git /japp && cd /japp && git checkout $JAPP_REF && \
    NO_SSE=1 scons -Q project=game debug=0 no_sql=1 no_crashhandler=1 no_notify=1 tools=default && \
    mkdir -p /opt/JediAcademy/japlus && cp "$(find /japp -name 'jampgamex86_64.so' | head -1)" /opt/JediAcademy/japlus/

FROM docker.io/library/ubuntu:24.04
RUN apt-get -q update && DEBIAN_FRONTEND=noninteractive apt-get -q install -y --no-install-recommends \
      python3 python3-aiohttp python3-pil zlib1g libstdc++6 tini && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/JediAcademy /opt/openjk
COPY server/gateway.py server/repack.py server/start.sh /opt/gateway/
COPY server/server.cfg /opt/openjk/base/server.cfg
# JPLua scripts of the JA++ mod (welcome message, /ammotd)
COPY server/japp/ /opt/openjk/japlus/
COPY dist-mp/ /opt/web/
RUN chmod +x /opt/gateway/start.sh /opt/openjk/openjkded.x86_64
ENV WEB_DIR=/opt/web DATA_DIR=/data/base GAME_HOST=127.0.0.1 GAME_PORT=29070 PORT=8080
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/gateway/start.sh"]
