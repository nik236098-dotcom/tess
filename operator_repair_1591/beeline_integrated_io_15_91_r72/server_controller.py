# r72 QUEUE_DONE — полный server_controller.py собирается из r71 + server_controller.patch
#
# На сервере:
#   cd /opt/beeline
#   cp server_controller.py server_controller.py.bak_r71
#   # скачать patch из репо и применить:
#   patch -p0 < server_controller.patch
#   # либо взять готовый файл из артефактов сборки
#
# Маркер после установки: grep QUEUE_DONE_1591R72 server_controller.py
#
# См. README.txt и server_controller.patch в этой папке.
raise SystemExit(
    "r72: замените этот файл на server_controller из r71, прогнанный через server_controller.patch"
)
