# Presenton RU — как запустить у себя и посмотреть

Это Presenton с русской локализацией (ветка `claude/i18n-ru`).
Ветка `main` — оригинальный Presenton без изменений, для сравнения.

## Что нужно

- **Docker Desktop** (Windows / macOS) или Docker + Compose (Linux), свободно ~8 ГБ ОЗУ и ~15 ГБ диска.
- **git**.

## Запуск

```bash
git clone -b claude/i18n-ru https://github.com/ilukinivan2018-beep/presenton-ru.git
cd presenton-ru
docker compose up production --build
```

Первая сборка идёт 15–30 минут (скачиваются зависимости), следующие запуски — секунды.
Когда в логе появится, что сервер запущен, откройте:

**http://localhost:5001**

- Первый экран — создание учётной записи администратора (логин и пароль придумываете сами, всё хранится локально в папке `app_data`).
- Интерфейс по умолчанию на русском. Язык переключается кнопками **RU / EN / Авто** в правом верхнем углу любого экрана; «Авто» — по языку браузера.
- **Помощь** (внизу боковой панели) — краткая справка на русском со ссылками на официальную документацию (она только на английском).
- Чтобы генерировать презентации, в мастере настройки нужно выбрать ИИ-провайдера и ввести его API-ключ. Без ключа можно пройти по интерфейсу: кабинет, шаблоны, настройки, редактор пустой презентации.

Остановить: `Ctrl+C` в терминале, затем `docker compose down`.

Если порт 5001 занят: `PRESENTON_HTTP_HOST_PORT=5002 docker compose up production --build`
(в PowerShell: `$env:PRESENTON_HTTP_HOST_PORT=5002; docker compose up production --build`).

## Где смотреть изменения

- Все правки относительно оригинала: https://github.com/ilukinivan2018-beep/presenton-ru/compare/main...claude/i18n-ru
- Описание работ, решений и способа проверки: [`LOCALIZATION_PLAN.md`](LOCALIZATION_PLAN.md) (раздел 12 — итоговый статус).
- Переводы интерфейса: `servers/nextjs/messages/ru.json` и `en.json`; сообщения бэкенда: `servers/fastapi/utils/i18n/`.
