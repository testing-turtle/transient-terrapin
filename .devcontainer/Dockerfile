FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# RUN npm install -g azure-functions-core-tools

RUN curl -sL https://aka.ms/DevTunnelCliInstall | bash

# TODO - doc login and tunnel creation
# devtunnel user login --github
# devtunnel create gh-webhook
# devtunnel port create gh-webhook -p 7071
# devtunnel host gh-webhook
# devtunnel access create gh-webhook --anonymous