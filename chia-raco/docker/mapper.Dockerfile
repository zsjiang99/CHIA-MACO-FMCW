FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git clang-12 llvm-12 llvm-12-dev llvm-12-tools ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root/cgra/CGRA-Mapper
COPY . .
RUN test "$(git rev-parse HEAD)" = 5f8393acb6b3a17146806ec93a57f76f875be232 \
    && cmake -S . -B build \
    && cmake --build build --parallel 2
