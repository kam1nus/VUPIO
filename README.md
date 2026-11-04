# VUPIO

## Скачать VUPIO

**[↓ Windows 11 x64](https://github.com/kam1nus/VUPIO/actions/runs/41825070187/artifacts/13318209269)** · **[↓ Mac с Apple Silicon (macOS 26+)](https://github.com/kam1nus/VUPIO/actions/runs/41825070187/artifacts/13319825525)**

Войдите в GitHub, скачайте и распакуйте ZIP, затем откройте установщик `.exe` или `.pkg`. [Страница сборки](https://github.com/kam1nus/VUPIO/actions/runs/41825070187).

Локальный саундборд, редактор аудио и пульт для телефона. Проект вырос из MIMIC. Существующая библиотека MIMIC на Mac остаётся в прежней папке.

## Обновления

**[Все релизы и список изменений](https://github.com/kam1nus/VUPIO/releases)**

В VUPIO откройте **Обновления → Проверить обновления**. Приложение покажет доступную сборку для вашей платформы и ссылку на установщик.

В сборке 4044 появился **Trend Radar** с региональными подборками. Мем-звуки проверяются и подгружаются заранее, недоступные записи заменяются следующими в чарте. Кнопка **Add** добавляет готовый звук в Soundboard.

## Сборки

| Платформа | Установщик | Что входит |
| --- | --- | --- |
| macOS 26+, Apple Silicon | `VUPIO-macOS-AppleSilicon.pkg` | Приложение, драйвер MIMIC Microphone, FFmpeg, llama.cpp, whisper.cpp и три модели |
| Windows 11 x64 | `VUPIO-Windows-x64-Setup.exe` | Приложение, FFmpeg, llama.cpp, whisper.cpp и три модели. При необходимости установщик скачает подписанный Microsoft Visual C++ Runtime |

В комплект входят модели Qwen2.5 0.5B Instruct для команд, Qwen3 Embedding 0.6B для смыслового поиска и Whisper Base для распознавания речи. Они проверяются по SHA-256 при сборке и при первом использовании. Для этих функций интернет, Python, Ollama и ключи API не нужны. Интернет-поиск по-прежнему использует внешний поисковый сервис с отдельными лимитами.

**Статус Alpha.** Установщики предназначены для тестирования. Пакет macOS без нотарификации Apple, установщик Windows без Authenticode. На Windows мастер VUPIO предлагает скачать драйвер напрямую у VB-Audio, проверяет хеш ZIP и цифровую подпись, затем открывает окно производителя. Пользователь подтверждает установку в этом окне.

## Проверка

### Mac

1. Закройте MIMIC, если он запущен. Откройте PKG и подтвердите установку.
2. Перезагрузите Mac для регистрации устройства. Откройте VUPIO в «Программах».
3. В Discord выберите **MIMIC Microphone** как вход, а наушники как выход.
4. В VUPIO включите физический микрофон, если хотите передавать голос. Подтвердите разрешение macOS при запросе.
5. В Discord запустите проверку микрофона и нажмите карточку в Soundboard.

Локальная Alpha-сборка имеет подпись для разработки. Для обычной публичной установки с проверкой Apple нужны Developer ID Application, Developer ID Installer и нотарификация. Тестовый PKG сам не меняет устройство Discord.

### Windows

1. Запустите `VUPIO-Windows-x64-Setup.exe`. Приложение откроет Soundboard в браузере. Оставьте небольшое окно VUPIO открытым.
2. Для Discord отметьте в мастере **«Скачать VB-CABLE»**, подтвердите установку в окне VB-Audio и перезагрузите Windows. При необходимости можно отдельно взять [установщик производителя](https://vb-audio.com/Cable/).
3. Откройте VUPIO. В **Settings → Audio Devices** выберите **CABLE Input** как выход, а свой физический микрофон как вход. Включите микрофон в VUPIO, если хотите передавать голос.
4. В Discord выберите **CABLE Output** как вход и физические наушники как выход. Если нужно одновременно слышать мемы, включите мониторинг клипов в VUPIO на наушники.
5. Проверьте голос и клипы через Discord Mic Test. В обычном звонке держите **Listen to this device** в настройках Windows выключенным, чтобы избежать двойного звука.

Windows использует WASAPI. Предпрослушивание играет в браузере, обычное нажатие на карточку передаёт звук в выбранный аудиовыход. Apple SoundAnalysis и специальные тесты Core Audio работают на Mac. Windows сохраняет распознавание Whisper, измерение звуковой волны, выбор по энергии и текстовый поиск.

### Пульт

Откройте **Remote** на компьютере, создайте QR и одноразовый код. На iPhone в той же локальной сети откройте QR в Safari, введите код и нажмите карточку. Для Windows разрешайте сетевой доступ только в частной сети. При переходе между Wi‑Fi и Ethernet перезапустите VUPIO. Проброс порта в интернет не нужен.

## Сборка разработчиком

В GitHub откройте **Actions → VUPIO preview installers → Run workflow**. Артефакты сборки появятся на странице прогона. Включите параметр **Publish** для публикации тестового релиза после успешной сборки обеих платформ.

- Mac Apple Silicon: `brew install ffmpeg cmake`, `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt pyinstaller==6.22.3`, затем `MIMIC_BUNDLE_MODELS=1 ./scripts/package.sh` и `./scripts/package_installer.sh`. Для подписанной сборки задайте `MIMIC_APP_SIGN_IDENTITY`, `MIMIC_INSTALLER_SIGN_IDENTITY` и `MIMIC_NOTARY_PROFILE`.
- Windows 11 x64: Python 3.14 и Inno Setup 6 требуются на машине сборки. Выполните `python -m pip install -r requirements-windows.txt`, затем `pwsh -File scripts/package_windows.ps1`.
- Результаты попадают в `build/releases`. Локальные данные хранятся в `~/Library/Application Support/MIMIC` и `%LOCALAPPDATA%\MIMIC`.

Перед публикацией с FFmpeg сохраните лицензии и обеспечьте доступ к соответствующим исходникам конкретных бинарных сборок и зависимостей. Сборка включает ссылки, контрольные суммы и лицензии в каталогах `Tools`, `Models` и `ThirdPartyLicenses`. Условия и исходники компонентов перечислены в [THIRD_PARTY.md](THIRD_PARTY.md).
