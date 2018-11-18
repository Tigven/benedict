#!/usr/bin/env python3
# coding: utf-8
import tornado.ioloop
import tornado.web
import json
from pymongo import MongoClient

from alice import AliceRequest, AliceResponse
from dialog import DialogHandler
from logger import get_logger

client = MongoClient('mongodb://127.0.0.1:27017/')
db = client.benedict


class BenedictHandler(tornado.web.RequestHandler):
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
    log = get_logger(app_name='server')
    app = make_app()
    app.listen(8088)
    tornado.ioloop.IOLoop.current().start()
