FROM python:3.7-slim

RUN apt-get update

RUN pip install pytest

ADD . /cogment-py-sdk
RUN pip install -e /cogment-py-sdk

WORKDIR /app

