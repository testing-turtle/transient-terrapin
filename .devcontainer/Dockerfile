FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# RUN npm install -g azure-functions-core-tools

RUN apt update && apt install -y xdg-utils
RUN curl -sL https://aka.ms/DevTunnelCliInstall | bash

# TODO - doc login and tunnel creation
# devtunnel user login --github
# devtunnel create gh-webhook
# devtunnel port create gh-webhook -p 7071
# devtunnel access create gh-webhook --anonymous
# devtunnel host gh-webhook

#run webhook2:  uvicorn main2:app --port 7071