import logging


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