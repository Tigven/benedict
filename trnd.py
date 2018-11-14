#!/usr/bin/env python3
# coding: utf-8

import tornado.ioloop
import tornado.web

import logging
import json
import random
from pymongo import MongoClient
from pymorphy2 import MorphAnalyzer

morph = MorphAnalyzer()

client = MongoClient('mongodb://127.0.0.1:27017/')
db = client.benedict
recipes = db.recipes


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

# Хранилища данных сессий
session_storage = {}

# Доступные навыки
all_suggests = [
    'Что я могу узнать?',
    'Сколько ты знаешь рецептов?',
]

# Токены для определения ключей команд
cmd_tokens = {
    'recipes_count':  {
        'necessarily': ['рецептов'],
        'one_of': ['сколько', ['как', 'много'], 'количество', 'число'],
    },
    'help':  {
        'one_of': [
            ['что', 'умеешь'], ['что', 'можешь'], ['что', 'знаешь'],
            ['что', 'подскажешь'], ['что', 'могу', 'узнать']
        ],
    },
    'find_recipe_by_name': {
        'one_of': [
            ['как', 'приготовить'], ['как', 'готовить'], ['подскажи', 'рецепт'],
            ['скажи', 'рецепт'], ['поищи', 'рецепт']
        ],
    },
    'find_recipe_by_ingredients': {
            'necessarily': ['из'],
            'one_of': [
                ['что', 'приготовить'], ['что', 'сделать'], ['рецепт'],
            ],
        },
}

def normalize_list(list):
    """Нормализация всех слов в списке"""
    return [morph.parse(l)[0].normal_form for l in list]



def get_recipes_count(tokens):
    rec_count = recipes.count_documents({})
    rec = morph.parse('рецепт')[0].make_agree_with_number(rec_count).word
    resp = 'На данный момент я знаю {} {}!'.format(rec_count, rec)
    return resp


def get_recipe_by_name(req):
    #tokens = normalize_list(tokens)
    tokens = req['request']['nlu']['tokens']
    if 'рецепт' in tokens:
        ind = tokens.index('рецепт')
    elif 'приготовить' in tokens:
        ind = tokens.index('приготовить')
    elif 'готовить' in tokens:
        ind = tokens.index('готовить')

    recipe_tokens = ' '.join(tokens[ind+1:])
    recipe_list = recipes.find_one({'$text': {'$search': recipe_tokens}})
    print(recipe_list.title)
    if not recipe_list:
        resp = 'К сожалению, я не знаю такого рецепта.'
    else:
        titles = [recipe.title for recipe in recipe_list]
        if len(titles) == 1:
            resp = 'Я нашел для вас рецепт {}.'.format(titles[-1])
        else:
            resp = 'Я нашел для вас следющие рецепты: {}.'.format(', '.join(titles))
    return resp


def get_recipe_by_ingredients(tokens):

    # recipe = recipes.find_one({'title'=''})
    resp = 'На данный момент я знаю около {}.'  # .format(recipes.count_documents({}))
    return resp


def get_help(req):
    resp = 'Я могу подобрать рецепт по ингредиентам и продиктовать пошаговые инструкции по приготовлению.' \
    'Просто спросите "Что приготовить из картошки?" или "Как приготовить карбонару?".'
    return resp


def get_command_key(tokens):
    """
    Получаение ключа команды по токенам.
    У каждой команды есть 2 списка токенов - обязательные и дополнительные.
    При поиске ставятся такие условия, что из *все* из обязательные токенов
    должны присутствовать в списке токенов запроса, и хотя бы *один из*
    дополнительных токенов.
    Элементы списка дополнительных токенов могут быть списками (тогда каждый
    из элементов такого списка элементов доп. токена должен присутствовать в
    списке токенов запроса).
    """
    for cmd_key, target_tokens in cmd_tokens.items():
        # Ищем необходимые для проверяемой команды токены, если они есть
        if len(target_tokens.get('necessarily', [])):
            for n_token in target_tokens['necessarily']:
                if n_token in tokens:
                    break
            else:
                # Если не нашли - переходим к проверке следующей команды
                continue

        # Проверяем, присутствет ли хотя бы один токен из
        # списка дополнительных токенов (должен быть хотя бы один),
        # если они есть
        if len(target_tokens.get('one_of', [])):
            for o_token in target_tokens['one_of']:
                if type(o_token) is list:
                    # Если элемент дополнительных токенов - список, то
                    # проверяем, что все элементы этого списка присутствуют
                    # в токенах запроса
                    for o_token_item in o_token:
                        if o_token_item not in tokens:
                            break
                    else:
                        # Если хотя все элементы из списка дополнительных
                        # токенов были найдены - заканчиваем проверку (ключ
                        # нужной команды найден)
                        break
                if o_token in tokens:
                    # Если хоть один из дополнительных токенов найдет -
                    # заканчиваем проверку (ключ нужной команды найден)
                    break
            else:
                # Если ни один из дополнительных токенов не был найден -
                # переходим к проверке следующей команды
                continue
        
        # Все (обязательные и дополнительные) токены были найдены в
        # списке токенов запроса - возвращаем ключ команды
        return cmd_key


def handle_dialog(req, resp):
    """
    Тут реализована логика обработки запроса.
    """
    user_id = req['session']['user_id']

    if req['session']['new']:
        # Обрабатываем запрос от нового пользователя.
        session_storage[user_id] = {
            'suggests': all_suggests,
        }

        resp['response']['text'] = 'Здравствуйте! Чем могу помочь?'
        resp['response']['buttons'] = get_suggests(user_id)
        return

    tokens = req['request']['nlu']['tokens']
    cmd_key = get_command_key(tokens)

    if cmd_key is None:
        resp['response']['text'] = 'Не могу это выполнить.'
    else:
        resp['response']['text'] = commands_map[cmd_key](req)


def get_suggests(user_id, num=4):
    """
    Возвращает подсказки для ответа
    """
    session = session_storage[user_id]
    suggests = session['suggests'][:]

    # Первая подсказка всегда будет отображаться
    result = [suggests.pop(0)]
    
    # Добавляем num-1 рандомных подсказок
    for i in range(num-1):
        random.shuffle(suggests)
        result.append(suggests.pop(0))

        # Если подсказок не осталось - выходим из
        # цикла заранее
        if not len(suggests):
            break

    suggests = [
        {'title': suggest, 'hide': True}
        for suggest in result
    ]

    return suggests


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

    def resp_meta(self, data):
        """
        Подготавливает JSON ответа в формате по протоколу:
        https://bit.ly/2CXhJnV
        """
        session = data.get('session', {})
        version = data.get('version', '1.0')

        return {
            'session': session,
            'version': version,
            'response': {
                'end_session': False,
            }
        }

    def get(self):
        output = "Benedict's recipes Alice API"
        self.write(self.format_resp(output))

    def post(self):
        # Парсим JSON запрос
        data = json.loads(self.request.body.decode())
        logger.info("Request: {}".format(json.dumps(data, indent=4)))

        # Подготавливаем мета поля ответа
        resp = self.resp_meta(data)
        # Подготавливаем сам ответ (содержание)
        handle_dialog(data, resp)
        logger.info("Response: {}".format(json.dumps(resp, indent=4)))

        self.write(self.format_resp(resp))


def make_app():
    return tornado.web.Application([
        (r"/benedict", BenedictHandler),
    ], debug=True)


if __name__ == "__main__":
    # Карта команд
    commands_map = {
        'recipes_count': get_recipes_count,
        'find_recipe_by_name': get_recipe_by_name,
        'find_recipe_by_ingredients': get_recipe_by_ingredients,
        'help': get_help,
    }

    logger = get_logger()
    app = make_app()
    app.listen(8088)
    tornado.ioloop.IOLoop.current().start()
