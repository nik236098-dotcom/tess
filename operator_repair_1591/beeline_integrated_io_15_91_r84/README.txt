15.91-io — ревизия 84 (QUEUE_DONE)

База: r83. Изменён только server_controller.py.

ЧТО ДОБАВЛЕНО
После окончания работы (очередь базы исчерпана, test_beeline сам вышел)
в Telegram уходит push:

  ✅ Работа завершена
  Отработано строк: N
  В базе сейчас: M

  [📥 Загрузить новую базу]  — callback m|basenew

Кнопка = тот же сценарий, что «📂 База → 🆕 Загрузить новую базу».

НЕ шлётся при:
- ручном ⏹ Остановить
- плановом перезапуске (exit code 75)

МАРКЕР: QUEUE_DONE_1591R84

УСТАНОВКА (точечная на сервере с r83)
1. sudo systemctl stop beeline
2. cp /opt/beeline/server_controller.py /opt/beeline/server_controller.py.bak_r83
3. Применить patch:
     cd /opt/beeline
     # скачать server_controller.patch из r84
     sed 's|server_controller_r83.py|server_controller.py|;s|server_controller_r84.py|server_controller.py|' server_controller.patch | patch -p0
4. grep -c QUEUE_DONE_1591R84 /opt/beeline/server_controller.py
5. sudo systemctl start beeline

Примечание: «r72» на feature/tg-autoreg был ошибочный черновик поверх старого кода — не ставить.
