15.91-io — ревизия 84 (QUEUE_DONE)

База: r83. Изменён только server_controller.py.

После конца базы в Telegram:
  ✅ Работа завершена
  Отработано строк: N
  [📥 Загрузить новую базу] (callback m|basenew)

Маркер: QUEUE_DONE_1591R84
Не шлётся при ручном Stop и плановом restart (exit 75).

УСТАНОВКА НА СЕРВЕРЕ (r83 уже стоит):
  sudo systemctl stop beeline
  cd /opt/beeline
  cp server_controller.py server_controller.py.bak_r83
  # скачать server_controller.patch из этой папки:
  curl -fsSL -o /tmp/sc84.patch \
    https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/operator_repair_1591/beeline_integrated_io_15_91_r84/server_controller.patch
  sed 's|server_controller_r83.py|server_controller.py|;s|server_controller_r84.py|server_controller.py|' \
    /tmp/sc84.patch | patch -p0
  grep -c QUEUE_DONE_1591R84 server_controller.py
  sudo systemctl start beeline

Полный install.py-пакет (beeline-update) — когда будут все файлы r83+controller;
сейчас «⬆️ Обновить» может показать r84, но ставить лучше через patch выше.
