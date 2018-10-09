from datetime import date, timedelta


def date_from_today(range_):
    return [date.today() + timedelta(days=delta) for delta in range_]


def russian_date(date_: date):
    if date_ == date.today():
        return 'Сегодня'
    if date_ == date.today() - date.resolution:
        return 'Вчера'
    if date_ == date.today() + date.resolution:
        return 'Завтра'
    return '{} {} ({})'.format(date_.day, russian_month(date_), russian_weekday(date_))


def russian_weekday(date_):
    return ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'][date_.weekday()]


def russian_month(date_):
    return ['Янв', 'Фев', 'Март', 'Апр', 'Май', 'Июнь', 'Июль', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'][date_.month]


def build_menu(buttons,
               n_cols,
               header_buttons=None,
               footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu
