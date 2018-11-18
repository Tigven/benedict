from pymorphy2 import MorphAnalyzer


class DialogHandler:
    morph = MorphAnalyzer()
    cmd_tokens = {
        'get_recipes_count': {
            'necessary': ['рецептов'],
            'one_of': ['сколько', ['как', 'много'], 'количество', 'число'],
        },
        'get_help': {
            'one_of': [
                ['что', 'умеешь'], ['что', 'можешь'], ['что', 'знаешь'],
                ['что', 'подскажешь'], ['что', 'могу', 'узнать']
            ],
        },
        'get_recipe_by_name': {
            'one_of': [
                ['как', 'приготовить'], ['как', 'готовить'], ['подскажи', 'рецепт'],
                ['скажи', 'рецепт'], ['поищи', 'рецепт']
            ],
        },
        'get_recipe_by_ingredients': {
            'necessary': ['из'],
            'one_of': [
                ['что', 'приготовить'], ['что', 'сделать'], ['рецепт'],
            ],
        },
        'repeat': {
            'one_of': [
                ['повтори'], ['еще', 'раз'], ['не', 'понял'], ["помедленнее"],
            ],
        },
    }

    def __init__(self, req, resp, db):
        self.req = req
        self.resp = resp
        self.db = db
        history = self.db.history.find_one({'user': self.req.user_id})
        if history is None:
            _id = self.db.history.insert_one({'user': self.req.user_id, 'history': list()}).inserted_id
            history = self.db.history.find_one({'_id': _id})
        self.history = history.get('history')
        self.session = self.db.sessions.find_one({'session': self.req.session})
        if not self.session:
            _id = self.db.sessions.insert_one({'session': self.req.session,
                                               'recipe': '',
                                               'step': 'start',
                                               'recipes_list': []}).inserted_id
            self.session = self.db.sessions.find_one({'_id': _id})
        recipe_name = self.session.get('recipe')
        self.recipe = self.db.recipes.find_one({'title': recipe_name}) if recipe_name else None

    def get_response(self):
        """
        Тут реализована логика обработки запроса.
        """
        if not self.req.is_new_session:
            self.process_req()
        else:
            # Обрабатываем запрос от нового пользователя.
            self.resp.set_text('Здравствуйте! Чем я могу Вам помочь?')
        self.history.extend([self.req.command, self.resp.get_text()])
        self.db.history.update_one({'user': self.req.user_id},
                                   {'$set':
                                       {'history': self.history}
                                    })
        return self.resp.dumps()

    def unknown(self):
        self.resp.set_text('Извините, я вас не совсем понял. Не могли бы переформулировать.')

    def process_req(self):
        """
        Вызов функции хендлера по токенам.
        У каждой команды есть 2 списка токенов - обязательные и дополнительные.
        При поиске ставятся такие условия, что из *все* из обязательные токенов
        должны присутствовать в списке токенов запроса, и хотя бы *один из*
        дополнительных токенов.
        Элементы списка дополнительных токенов могут быть списками (тогда каждый
        из элементов такого списка элементов доп. токена должен присутствовать в
        списке токенов запроса).
        """

        tokens = self.req.tokens
        step = self.session.get('step')
        if step == 'recipes_list':
            num = self.req.get_number()
            if num:
                recipe_title = self.session.get('recipes_list')[num]
                self.db.session.update_one({'session': self.req.session},
                                           {'$set':
                                               {'recipe': recipe_title,
                                                'step': 'recipe_selected'}
                                            })

                self.start_recipe(recipe_title)
                return
        elif type(step) == int:
            self.recipe_step(step)
            return
        elif step == 'finish':
            self.resp.set_text('Чем я еще могу Вам помочь?')
            return
        for handler, target_tokens in self.cmd_tokens.items():
            # Ищем необходимые для проверяемой команды токены, если они есть
            if len(target_tokens.get('necessary', [])):
                for n_token in target_tokens['necessary']:
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
            # списке токенов запроса - вызываем хендлер
            getattr(self, handler, self.unknown)()

    def get_recipes_count(self):
        rec_count = self.db.recipes.count_documents({})
        rec = self.morph.parse('рецепт')[0].make_agree_with_number(rec_count).word
        self.resp.set_text('На данный момент я знаю {} {}!'.format(rec_count, rec))

    def get_recipe_by_name(self):
        tokens = self.req.tokens
        if 'рецепт' in tokens:
            ind = tokens.index('рецепт')
        elif 'приготовить' in tokens:
            ind = tokens.index('приготовить')
        elif 'готовить' in tokens:
            ind = tokens.index('готовить')

        recipe_tokens = ' '.join(tokens[ind + 1:])
        recipe_list = self.db.recipes.find(
            {'$text': {'$search': recipe_tokens}},
            {'score': {'$meta': "textScore"}}).sort(
            [('score', {'$meta': "textScore"})]).limit(3)
        if not recipe_list:
            resp = 'К сожалению, я не знаю такого рецепта.'
        else:
            titles = [recipe.get('title') for recipe in recipe_list]
            if len(titles) == 1:
                resp = 'Я нашел для вас рецепт {}.'.format(titles[-1])
                self.db.session.update_one({'session': self.req.session},
                                           {'$set':
                                               {'recipe': titles[-1],
                                                'step': 'recipe_selected'}
                                            })
            else:
                resp = 'Я нашел для вас следющие рецепты: {}. Что будем готовить?'.format(', '.join(titles))
                self.db.session.update_one({'session': self.req.session},
                                           {'$set':
                                               {'recipes_list': titles,
                                                'step': 'recipes_list'}
                                            })
        self.resp.set_text(resp)

    def get_recipe_by_ingredients(self):
        tokens = self.req.tokens
        ind = tokens.index('из')
        if 'без' in tokens:
            ind_2 = tokens.index('без')
            include_ingr = tokens[ind + 1: ind_2]
            exclude_ingr = tokens[ind_2 + 1:]
            if len(exclude_ingr) == 1:
                exclude_ingr = ' -' + exclude_ingr[0]
            else:
                exclude_ingr = ' -'.join(exclude_ingr)
            recipe_list = self.db.recipes.find({'$text': {'$search': (' '.join(include_ingr) + exclude_ingr)}},
                                               {'score': {'$meta': "textScore"}}).sort(
                                               [('score', {'$meta': "textScore"})]).limit(3)
        else:
            include_ingr = tokens[ind + 1:]
            recipe_list = self.db.recipes.find({'$text': {'$search': ' '.join(include_ingr)}},
                                       {'score': {'$meta': "textScore"}}).sort(
                [('score', {'$meta': "textScore"})]).limit(3)
        if not recipe_list:
            resp = 'К сожалению, я не знаю такого рецепта.'
        else:
            titles = [recipe.get('title') for recipe in recipe_list]

        if len(titles) == 0:
            resp = 'К сожалению, я не знаю такого рецепта.'
        elif len(titles) == 1:
            resp = 'Я нашел для вас рецепт {}.'.format(titles[-1])
        else:
            resp = 'Я нашел для вас следющие рецепты: {}.'.format(', '.join(titles))
        self.db.session.update_one({'session': self.req.session},
                                   {'$set':
                                       {'recipes_list': titles}
                                    })
        self.resp.set_text(resp)

    def get_help(self):
        self.resp.set_text('Я могу подобрать рецепт по ингредиентам и продиктовать пошаговые инструкции '
                           'по приготовлению. Просто спросите "Что приготовить из кабачков?" или '
                           '"Как приготовить карбонару?".')

    def repeat(self):
        if len(self.history):
            self.resp.set_text(self.history[-1])
        else:
            self.unknown()

    def start_recipe(self, recipe_title):
        recipe = self.db.recipes.find_one({'title': recipe_title})
        title = recipe.get('title')
        steps = recipe.get('steps')
        self.resp.set_text(steps[0])
        self.db.session.update_one({'session': self.req.session},
                                   {'$set':
                                       {'recipe': title,
                                        'step': 1},
                                    }
                                   )

    def recipe_step(self, step_num):

        recipe = self.db.recipes.find_one({'title': self.session.get('recipe')})
        steps = recipe.get('steps')
        if len(steps) == step_num:
            self.resp.set_text('Готово! Приятного аппетита!')
            self.db.session.update_one({'session': self.req.session},
                                       {'$set':
                                           {'step': 'finish'},
                                        }
                                       )
        else:
            self.resp.set_text(steps[step_num])
            self.db.session.update_one({'session': self.req.session},
                                       {'$set':
                                           {'step': step_num + 1},
                                        }
                                       )

