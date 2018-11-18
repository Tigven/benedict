#!/usr/bin/env python3
# coding: utf-8

import tornado.ioloop
import tornado.web

import logging
import json
from pymongo import MongoClient

from sdk import AliceRequest, AliceResponse
from dialog import DialogHandler

client = MongoClient('mongodb://127.0.0.1:27017/')
db = client.benedict


def get_logger(app_name=__file__, path="./"):
    """
    Конфигурируем логирование и возвращаем объект, через
    который можно будет писать логи с этими настройками.
    """
    lvl = logging.DEBUG
    filename = "{}{}.log".format(path, app_name)
    format_str = "%(asctime)s - %(message)s"
    formatter = logging.Formatter(format_str)

    logger = logging.getLogger(app_name)
    logger.setLevel(lvl)

    fh = logging.FileHandler(filename)
    ch = logging.StreamHandler()

    fh.setLevel(lvl)
    ch.setLevel(lvl)

    ch.setFormatter(formatter)
    fh.setFormatter(formatter)

    logger.addHandler(ch)
    logger.addHandler(fh)

    return logger


class BenedictHandler(tornado.web.RequestHandler):
    def set_default_headers(self, *args, **kwargs):
        pass

    def format_resp(self, data, fmt='json'):
        """
        Переводит ответ в нужный формат и выставляет соответстующие
        HTTP заголовки.
        По умолчанию ответ конвертируется в JSON.
        """
        if fmt == 'json':
            self.set_header("Content-Type", "application/json")
            data = json.dumps(data, default=str)

        return data

    def get(self):
        output = "Benedict's recipes Alice API"
        self.write(self.format_resp(output))

    def post(self):
        alice_request = AliceRequest(json.loads(self.request.body.decode()))
        alice_response = AliceResponse(alice_request)
        self.write(DialogHandler(alice_request, alice_response, db).get_response())


def make_app():
    return tornado.web.Application([
        (r"/benedict", BenedictHandler),
    ], debug=True)


if __name__ == "__main__":
    logger = get_logger()
    app = make_app()
    app.listen(8088)
    tornado.ioloop.IOLoop.current().start()
