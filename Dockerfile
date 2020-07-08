FROM python:3.8.3-slim-buster

RUN apt-get update

RUN pip install pytest

WORKDIR /app

ADD . /cogment-py-sdk

RUN cd /cogment-py-sdk && pip install -e .