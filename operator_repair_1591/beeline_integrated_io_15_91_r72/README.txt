15.91-io — ревизия 72 (QUEUE_DONE)

ЧТО ДОБАВЛЕНО
После окончания работы (очередь базы исчерпана, процесс test_beeline сам вышел)
контроллер шлёт в Telegram push:

  ✅ Работа завершена
  Отработано строк: N
  В базе сейчас: M   (если clients.txt ещё есть)

  [📥 Загрузить новую базу]   — inline-кнопка (callback m|basenew)

Кнопка открывает тот же сценарий загрузки, что и «📂 База → 🆕 Загрузить новую базу».
После нажатия пришлите .txt следующим сообщением.

ЧТО НЕ ТРОГАЕТСЯ
- Ручной «⏹ Остановить» — пуш «работа завершена» НЕ уходит
- Плановый перезапуск (exit code 75 / drain) — НЕ уходит (как раньше, своё сообщение)
- test_beeline.py, telegram_menu.py, матчер — без изменений

МАРКЕР
QUEUE_DONE_1591R72

ФАЙЛ
Изменён только server_controller.py относительно r71.

УСТАНОВКА (точечная)
1. Остановить службу: sudo systemctl stop beeline
2. Бэкап: cp /opt/beeline/server_controller.py /opt/beeline/server_controller.py.bak_r71
3. Положить server_controller.py из этой папки в /opt/beeline/
   (или: patch -p0 < server_controller.patch из копии r71)
4. sudo systemctl start beeline
5. grep -c QUEUE_DONE_1591R72 /opt/beeline/server_controller.py

Проверка: конец базы → push с кнопкой загрузки.
