#!/bin/bash

# Docker variables
USER=$(id -u)
GROUP=$(id -g)

# Build docker image
docker build --build-arg UID="$USER" --build-arg GID="$GROUP" \
             . --tag stomp

# Run docker shell
docker run -it --shm-size 256m --hostname stomp -u "$USER" \
           -v "/home/$(whoami)/.ssh:/home/dev-user/.ssh" \
           -v "$(pwd):/workspace" \
           stomp:latest /bin/bash
