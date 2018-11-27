from pymorphy2 import MorphAnalyzer
from logger import get_logger
import random

log = get_logger(app_name='dialog')
morph = MorphAnalyzer()


def normalize(obj):
    if type(obj) == str:
        obj = obj.split(' ')
    return [morph.parse(word)[0].normal_form for word in obj]


def choose_closest(tokens, choices):
    tokens = normalize(tokens)
    score = dict()
    for choice in choices:
        score[choice] = 0
        normalized_choice = normalize(choice)
        for word in normalized_choice:
            if word in tokens:
                score[choice] += 1
            else:
                score[choice] -= 0.1
    t = [(k, v) for k, v in score.items()]
    t.sort(key=lambda x: x[1])
    if t[-1][1] == 0:
        return None
    return t[-1][0]


def inflect(string, inflect_to):
    ans = []
    transform = True
    for i, word in enumerate(string.split(' ')):
        w = morph.parse(word)[0].inflect({inflect_to})
        if w and transform:
            ans.append(w.word)
            if 'NOUN' in w.tag:
                transform = False
        else:
            ans.append(word)
    return ' '.join(ans)


class DialogHandler:
    morph = MorphAnalyzer()
    main_tokens = {
        'get_recipes_count': {
            'necessary': ['рецептов'],
            'one_of': ['сколько', ['как', 'много'], 'количество', 'число'],
        },
        'get_help_main': {
            'one_of': [
                ['что', 'умеешь'], ['что', 'можешь'], ['что', 'знаешь'],
                ['что', 'подскажешь'], ['что', 'могу', 'узнать'], 'помощь'
            ],
        },
        'get_recipe_by_name': {
            'one_of': [
                ['как', 'приготовить'], ['как', 'готовить'], ['подскажи', 'рецепт'],
                ['скажи', 'рецепт'], ['поищи', 'рецепт'], ['рецепт']
            ],
        },
        'get_recipe_by_ingredients': {
            'necessary': ['из'],
            'one_of': [
                ['что', 'приготовить'], ['что', 'сделать'], 'рецепт',
            ],
        },
        'repeat': {
            'one_of': ['повтори', ['еще', 'раз'], ['не', 'понял'], "помедленнее"],
        },
        'hello': {
            'one_of': ['привет', 'здравствуй', 'здарова'],
        },
        'thank': {
            'one_of': ['спасибо'],
        },
        'nutrients': {
            'necessary': ['сколько'],
            'one_of': ['белков', 'жиров', 'углеводов', 'калорий'],
        },
    }

    step_tokens = {
        'recipe_step_forward': {
            'one_of': ['дальше', "вперед", "готово", 'хорошо', 'ок', "да", 'приступаем', 'поехали']
        },
        'recipe_step_backward': {
            'one_of': ['назад', "вернись", ['еще', 'раз']]
        },
        'stop': {
            'one_of': ['остановись', "стоп", "хватит", ['другой', "рецепт"]]
        },
        'time': {
            'one_of': [['сколько', 'времени'], ['сколько', 'готовить'], ['долго', 'готовить']],
        },
        'nutrients': {
            'necessary': ['сколько'],
            'one_of': ['белков', 'жиров', 'углеводов', 'калорий'],
        },
        'get_help_step': {
            'one_of': [
                ['что', 'умеешь'], ['что', 'можешь'], ['что', 'знаешь'],
                ['что', 'подскажешь'], ['что', 'могу', 'узнать'], 'помощь'
            ],
        },
        'repeat': {
            'one_of': ['повтори', ['еще', 'раз'], ['не', 'понял'], "помедленнее"],
        },
    }

    recipe_list_tokens = {
        'next_recipes_page': {
            'one_of': ['дальше', 'еще', 'следующая', 'следующие', 'вперед'],
        },
        'prev_recipes_page': {
            'one_of': ['назад', 'предыдущая', 'предыдущие'],
        },
        'stop': {
            'one_of': ['стоп', 'другой']
        },
        'get_help_rec_list': {
            'one_of': [
                ['что', 'умеешь'], ['что', 'можешь'], ['что', 'знаешь'],
                ['что', 'подскажешь'], ['что', 'могу', 'узнать'], 'помощь'
            ],
        },
        'repeat': {
            'one_of': ['повтори', ['еще', 'раз'], ['не', 'понял'], "помедленнее"],
        },
    }

    recipe_selected_tokens = {
        'start_recipe': {
            'one_of': ['дальше', 'еще', 'следующая', 'следующие', 'вперед', 'поехали', 'начинаем',
                       "да", "готово", "ага", "угу", "есть"],
        },
        'stop': {
            'one_of': ['стоп', 'другой']
        },
        'get_help_rec_sel': {
            'one_of': [
                ['что', 'умеешь'], ['что', 'можешь'], ['что', 'знаешь'],
                ['что', 'подскажешь'], ['что', 'могу', 'узнать'], 'помощь'
            ],
        },
        'repeat': {
            'one_of': ['повтори', ['еще', 'раз'], ['не', 'понял'], "помедленнее"],
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
        self.session = self.db.sessions.find_one({'session': self.req.session.get('session_id')})
        if not self.session:
            _id = self.db.sessions.insert_one({'session': self.req.session.get('session_id'),
                                               'recipe': '',
                                               'step': 'start',
                                               'recipes_list': [],
                                               'page': 0}).inserted_id
            self.session = self.db.sessions.find_one({'_id': _id})

    def get_response(self):
        """
        Тут реализована логика обработки запроса.
        """
        if not self.req.is_new_session:
            self.resp.set_text('Извините, я вас не совсем понял. Не могли бы переформулировать.')
            self.process_req()
        else:
            # Обрабатываем запрос от нового пользователя.
            if self.req.command == '':
                self.resp.set_text('Здравствуйте! Я могу подобрать рецепт по ингредиентам и продиктовать пошаговые '
                                   'инструкции по приготовлению. Просто спросите "Что приготовить из шампиньонов?" или '
                                   '"Как приготовить карбонару?"')
            else:
                self.process_req()
        self.history.extend([self.req.command, self.resp.get_text()])
        self.db.history.update_one({'user': self.req.user_id},
                                   {'$set': {'history': self.history}})
        return self.resp.dumps()

    def unknown(self):
        choices = ['Извините, я вас не совсем понял. Не могли бы переформулировать.']
        self.resp.set_text(random.choice(choices))

    def choose_recipe(self):
        page = self.session.get('page')
        idx = page * 3
        num = self.req.get_number()
        recipes_page = self.session.get('recipes_list')[idx:idx+3]
        if num and num < len(recipes_page):
            recipe_title = recipes_page[num - 1]
        else:
            recipe_title = choose_closest(self.req.tokens, recipes_page)
            log.debug('choosen recipe is {}, list is {}'.format(recipe_title,
                                                                recipes_page))
            if recipe_title is None:
                return self.get_help_rec_list()
        self.session['recipe'] = recipe_title
        self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                    {'$set': {'recipe': recipe_title, 'step': 'recipe_selected', 'page': -1}})
        self.start_recipe()

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
        log.debug('current step is {}'.format(step))
        if step == 'recipes_list':
            self.process_tokens(tokens, self.recipe_list_tokens, default=self.choose_recipe)
        elif step == 'recipe':
            self.process_tokens(tokens, self.step_tokens, default=self.get_help_step)
        elif step == 'recipe_selected':
            self.process_tokens(tokens, self.recipe_selected_tokens, default=self.get_help_rec_sel)
        else:
            self.process_tokens(tokens, self.main_tokens, default=self.get_help_main)

    def process_tokens(self, tokens, token_list, default):
        for handler, target_tokens in token_list.items():
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
            log.debug('Choosen handler is {}'.format(handler))
            getattr(self, handler, default)()
            return
        default()

    def resp_from_recipe_list(self, recipe_list):
        titles = [recipe.get('title') for recipe in recipe_list]
        if len(titles) == 0:
            resp = 'К сожалению, я не знаю такого рецепта. Давайте поищем что нибудь другое.'
            self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                        {'$set': {'step': 'start'}})
        elif len(titles) == 1:
            self.db.sessions.update_one(
                {'session': self.req.session.get('session_id')},
                {'$set':
                     {'recipe': titles[-1],
                      'step': 'recipe_selected'}})
            resp = 'Я нашел для вас рецепт {}. Приступаем?'.format(titles[-1])

        elif len(titles) > 3:
            rec = morph.parse('рецепт')[0].make_agree_with_number(len(titles)).word
            resp = 'Я нашел для вас {} {}. Самые популярные это {}. Что нибудь понравилось или ищем дальше?'.format(
                len(titles), rec, ', '.join(titles[:3]))
            self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                        {'$set': {'recipes_list': titles, 'step': 'recipes_list', 'page': 0}})
        else:
            resp = 'Я нашел для вас следующие рецепты: {}. Что будем готовить?'.format(', '.join(titles[:3]))
            self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                        {'$set': {'recipes_list': titles, 'step': 'recipes_list', 'page': 0}})
        self.resp.set_text(resp)

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
            [('score', {'$meta': "textScore"})]).limit(10)

        self.resp_from_recipe_list(recipe_list)

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
                                                   [('score', {'$meta': "textScore"})]).limit(12)
        else:
            include_ingr = tokens[ind + 1:]
            recipe_list = self.db.recipes.find({'$text': {'$search': ' '.join(include_ingr)}},
                                               {'score': {'$meta': "textScore"}}).sort(
                                                   [('score', {'$meta': "textScore"})]).limit(12)

        self.resp_from_recipe_list(recipe_list)

    def start_recipe(self):
        recipe_title = self.session.get('recipe')
        recipe = self.db.recipes.find_one({'title': recipe_title})
        title = recipe.get('title')
        ingredients = recipe.get('ingredients')
        ingrs_str = ''
        for ingr in ingredients:
            ingrs_str = '{}{} - {}, '.format(ingrs_str, ingr.get('name'), ingr.get('amount'))
        portions = recipe.get('portions')
        resp = "Готовим {}. Чтобы приготовить {} Вам понадобится: {}. Приступаем?".format(title, portions, ingrs_str)
        self.resp.set_text(resp)
        self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                    {'$set': {'step': 'recipe', 'page': -1}})

    def recipe_step_forward(self):
        recipe = self.db.recipes.find_one({'title': self.session.get('recipe')})
        step_num = self.session.get('page') + 1
        steps = recipe.get('steps')
        if len(steps) == step_num:
            self.resp.set_text('Готово! Приятного аппетита! Чем я еще могу Вам помочь?')
            self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                        {'$set': {'step': 'start'}})
        else:
            self.resp.set_text(steps[step_num])
            self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                        {'$set': {'page': step_num}})

    def recipe_step_backward(self):
        recipe = self.db.recipes.find_one({'title': self.session.get('recipe')})
        step_num = self.session.get('page') - 1
        if step_num < 0:
            step_num = 0
        steps = recipe.get('steps')
        self.resp.set_text(steps[step_num])
        self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                    {'$set': {'page': step_num}})

    def nutrients(self):
        recipe = self.db.recipes.find_one({'title': self.session.get('recipe')})
        title = recipe.get('title')
        if not title:
            return self.get_help_step()
        nutrs = recipe.get('nutrients')
        for nutr in nutrs:
            if nutr['name'] == 'Калорийность':
                cal = '{} {} '.format(nutr['amount'], nutr['unit'])
            elif nutr['name'] == 'Белки':
                prot = '{} {} '.format(nutr['amount'], nutr['unit'])
            elif nutr['name'] == 'Жиры':
                fat = '{} {} '.format(nutr['amount'], nutr['unit'])
            elif nutr['name'] == 'Углеводы':
                carb = '{} {} '.format(nutr['amount'], nutr['unit'])

        self.resp.set_text('В одной порции {} содержится {},'
                           ' {} белков, {} жиров, {} углеводов'.format(inflect(title, 'gent'),
                                                                       cal, prot, fat, carb))

    def next_recipes_page(self):
        titles = self.session.get('recipes_list')
        page = self.session.get('page') + 1
        if page * 3 >= len(titles):
            page = 0
            resp = 'Мы уже пошли по второму кругу. {}.'.format(', '.join(titles[:3]))
        else:
            idx = page*3
            resp = '{}.'.format(', '.join(titles[idx:idx+3]))
        self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                    {'$set': {'page': page}})
        self.resp.set_text(resp)

    def prev_recipes_page(self):
        titles = self.session.get('recipes_list')
        page = self.session.get('page') - 1
        if page < 0:
            page += 1
        idx = page * 3
        resp = '{}.'.format(', '.join(titles[idx:idx + 3]))
        self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                    {'$set': {'page': page}})
        self.resp.set_text(resp)

    def get_recipes_count(self):
        rec_count = self.db.recipes.count_documents({})
        rec = morph.parse('рецепт')[0].make_agree_with_number(rec_count).word
        self.resp.set_text('На данный момент я знаю {} {}!'.format(rec_count, rec))

    def hello(self):
        self.resp.set_text('Здравствуйте! Чем я могу Вам помочь?')

    def thank(self):
        self.resp.set_text('Пожалуйста! Чем ещё я могу Вам помочь?')

    def stop(self):
        self.resp.set_text('Хорошо! Чем я еще могу Вам помочь?')
        self.db.sessions.update_one({'session': self.req.session.get('session_id')},
                                    {'$set': {'step': 'start'}})

    def time(self):
        recipe = self.db.recipes.find_one({'title': self.session.get('recipe')})
        t = recipe.get('time')
        self.resp.set_text('Время приготовления {}'.format(t))

    def get_help_main(self):
        self.resp.set_text('Я могу подобрать рецепт по ингредиентам и продиктовать пошаговые инструкции '
                           'по приготовлению. Просто спросите "Что приготовить из кабачков без сыра" или '
                           '"Как приготовить карбонару?". '
                           'Чтобы получить подсказку скажите "Помощь" в любой момент диалога.')

    def get_help_step(self):
        self.resp.set_text('Чтобы перейти к следующему шагу скажите "Дальше", '
                           'чтобы вернуться к предыдущему скажите "Назад". '
                           'Так же можете спросить "Как долго готовить?", '
                           '"Сколько калорий, белков, жиров или углеводов?". '
                           'Чтобы поискать другой рецепт скажите "Стоп".')

    def get_help_rec_list(self):
        self.resp.set_text('Для выбора рецепта назовите его номер или название. '
                           'Чтобы перейти к следующим рецептам скажите "Дальше", '
                           'чтобы вернуться к предыдущим рецептам скажите "Назад". '
                           'Чтобы поискать другой рецепт скажите "Стоп".')

    def get_help_rec_sel(self):
        self.resp.set_text('Чтобы начать готовить скажите "Дальше".'
                           'Чтобы поискать другой рецепт скажите "Стоп".')

    def repeat(self):
        if len(self.history):
            self.resp.set_text(self.history[-1])
        else:
            self.unknown()
