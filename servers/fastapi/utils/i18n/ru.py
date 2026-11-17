# Russian backend messages (default UI locale). Keep keys and {placeholders}
# identical to en.py; tests/unit/test_i18n.py enforces parity. Avoid literal
# braces.

MESSAGES: dict[str, str] = {
    # Session / auth
    "auth.unauthorized": "Требуется авторизация",
    "auth.setupRequired": "Сначала нужно создать учётную запись администратора",
    "auth.adminSessionRequired": "Действие доступно только администратору, вошедшему через браузер",
    "auth.assetNotFound": "Файл не найден",
    "auth.assetAccessDenied": "Нет доступа к файлу",
    "auth.credentialsConfigured": "Учётная запись администратора уже создана",
    "auth.registrationClosed": "Регистрация сейчас закрыта",
    "auth.consentRequired": "Нужно принять оферту и согласиться на обработку персональных данных",
    "auth.emailInvalid": "Проверьте адрес электронной почты",
    "auth.emailDisposable": "Одноразовые почтовые ящики не подходят — укажите постоянный адрес",
    "auth.emailTaken": "Этот e-mail уже зарегистрирован — войдите или восстановите пароль",
    "auth.captchaFailed": "Подтвердите, что вы не робот",
    "auth.tooManyRegistrations": "Слишком много регистраций с вашего адреса. Попробуйте завтра",
    "auth.tooManyLetters": "Письмо уже отправлено. Повторить можно через час",
    "auth.linkInvalid": "Ссылка устарела или уже использована. Запросите новую",
    "auth.mailUnavailable": "Отправка писем пока не настроена. Обратитесь к администратору",
    "auth.mailFailed": "Не удалось отправить письмо. Попробуйте позже",
    "auth.mailRequired": "Сначала настройте почту: {missing}",
    "auth.mailTestFailed": "Письмо не отправлено: {error}",
    "auth.documentNotFound": "Документ не найден",
    "auth.usernameTooShort": "Имя пользователя должно быть не короче {min} симв.",
    # Admin panel
    "admin.activeUserNotFound": "Активный пользователь не найден",
    "admin.apiKeyNotFound": "API-ключ не найден",
    "admin.apiKeyRevoked": "API-ключ отозван",
    "admin.apiKeyCannotReveal": "Этот API-ключ нельзя показать",
    "admin.adminAccessRequired": "Требуются права администратора",
    "admin.forbidden": "У вас нет доступа к этому ресурсу",
    "admin.usernameExists": "Пользователь с таким именем уже существует",
    "admin.userNotFound": "Пользователь не найден",
    "admin.primaryPasswordManaged": "Пароль основного администратора задаётся в настройках развёртывания",
    "admin.primaryCannotDelete": "Учётную запись основного администратора нельзя удалить",
    # AI provider failures (shown in generation / settings)
    "provider.invalidApiKey": "Неверный API-ключ. Проверьте ключ и попробуйте снова.",
    "provider.imageModeration": "Запрос изображения заблокирован системой безопасности. Для этого слайда использовано изображение-заглушка.",
    "provider.generic": "ИИ-провайдер вернул ошибку. Попробуйте снова.",
    "provider.safetyBlocked": "Запрос заблокирован системой безопасности провайдера. Измените его и попробуйте снова.",
    "provider.prefix": "{provider} ({operation})",
    "provider.aiProvider": "ИИ-провайдер",
    "provider.op.request": "запрос",
    "provider.op.apiRequest": "запрос к API",
    "provider.op.imageGeneration": "генерация изображения",
    "provider.op.modelValidation": "проверка модели",
    "provider.quotaUnavailable": "{prefix}: ошибка — квота API недоступна. Проверьте оплату API {provider} и лимиты проекта, которому принадлежит этот ключ.",
    "provider.forbidden": "{provider} отклонил запрос: у настроенного API-ключа нет доступа. Проверьте права ключа и выбранную модель.",
    "provider.rateLimited": "{prefix}: превышен лимит запросов. Подождите немного и попробуйте снова.",
    "provider.modelUnavailable": "Выбранная модель {provider} недоступна. Выберите другую модель или проверьте доступ к ней.",
    "provider.failed": "{prefix}: ошибка. Попробуйте снова.",
    "presentation.untitled": "Презентация без названия",
}

# Request validation (422), keyed by pydantic error ``type``; placeholders come
# from the error's ``ctx``.
VALIDATION_MESSAGES: dict[str, str] = {
    "missing": "Обязательное поле",
    "extra_forbidden": "Лишнее поле не допускается",
    "string_type": "Ожидается строка",
    "string_too_short": "Должно быть не короче {min_length} симв.",
    "string_too_long": "Должно быть не длиннее {max_length} симв.",
    "string_pattern_mismatch": "Недопустимый формат значения",
    "int_type": "Ожидается целое число",
    "int_parsing": "Ожидается целое число",
    "int_from_float": "Ожидается целое число",
    "float_type": "Ожидается число",
    "float_parsing": "Ожидается число",
    "bool_type": "Ожидается логическое значение (true/false)",
    "bool_parsing": "Ожидается логическое значение (true/false)",
    "greater_than": "Значение должно быть больше {gt}",
    "greater_than_equal": "Значение должно быть не меньше {ge}",
    "less_than": "Значение должно быть меньше {lt}",
    "less_than_equal": "Значение должно быть не больше {le}",
    "too_short": "Слишком мало элементов: нужно не меньше {min_length}",
    "too_long": "Слишком много элементов: допускается не больше {max_length}",
    "list_type": "Ожидается список",
    "dict_type": "Ожидается объект",
    "model_type": "Ожидается объект",
    "model_attributes_type": "Ожидается объект",
    "json_invalid": "Некорректный JSON",
    "json_type": "Ожидается JSON",
    "uuid_type": "Некорректный идентификатор (UUID)",
    "uuid_parsing": "Некорректный идентификатор (UUID)",
    "enum": "Допустимые значения: {expected}",
    "literal_error": "Допустимые значения: {expected}",
    "url_type": "Ожидается URL",
    "url_parsing": "Некорректный URL",
    "date_parsing": "Некорректная дата",
    "datetime_parsing": "Некорректные дата и время",
}


# Backend HTTP error texts (see errors_ru.py).
from utils.i18n.errors_ru import ERRORS as _ERRORS  # noqa: E402

MESSAGES.update(_ERRORS)
