FROM python:3.7

RUN apt-get update

RUN pip install pytest

WORKDIR /app

ADD . /app

RUN pip install -e .