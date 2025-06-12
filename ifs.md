```bash
# 1. Проверяем, что диск есть
diskutil list | grep 22.0T

# 2. Проверяем модули
kextstat | grep lundman || sudo kextload /Library/Extensions/{spl,zfs}.kext

# 3. Смотрим, какие пулы доступны
sudo zpool import

# 4. Импортируем пул "media" в /Volumes/media
sudo mkdir -p /Volumes/media
sudo zpool import -f -R /Volumes/media media

# 5. Монтируем все ФС пула
sudo zfs mount -a

# 6. Проверяем
zfs list -r media
df -h | grep media
```

```bash
zpool status -x          # 1. ошибок нет?
lsof +D /Volumes/media   # 2. файлы закрыты?
zpool sync media         # 3. всё записано?
zpool export media       # 4. пул экспортирован?
diskutil eject /dev/disk3# 5. диск «выброшен»?
                         # 6. дождитесь, пока диск пропадёт → выключайте питание

```
