Когда вы нажали **Ignore**, macOS просто решила не монтировать тома, но сам USB-устройство осталось «видимым» в системе — поэтому диск всё ещё шумит и питается. Ниже — краткий конспект, а затем подробная инструкция для macOS и Linux.

> **Итог в одном абзаце**
> • На Mac достаточно «выбросить» (eject) именно *устройство*, а не отдельные тома: Finder-кнопка ⏏ или `diskutil eject /dev/diskN` одновременно размонтирует все разделы, пошлёт команде SCSI/USB «STOP UNIT» и переведёт питание порта в режим U-Suspend — диск замирает и можно выдёргивать кабель.
> • В Linux делаем то же: `udisksctl unmount -b /dev/sdX1` для разделов → `udisksctl power-off -b /dev/sdX` для самого диска; либо через GUI **GNOME Disks** → «Power Off». Оба варианта сначала синхронизируют кэш, потом выключают шину, и шпиндель останавливается.
> • Простое `umount` или «Eject том» снимает файловую систему, но питание оставляет — диск продолжит крутиться.
> • Перед отключением убедитесь, что LED погас или слышно, как диски остановились.

---

## 1 . macOS (Intel и Apple Silicon одинаково)

### 1.1 GUI-способ

1. Откройте **Disk Utility → View → Show All Devices**.
2. В левой колонке выберите верхний пункт «22 TB USB External Media» (это само устройство, а не его раздел).
3. Нажмите значок ⏏ или пункт «Eject». После успеха том пропадёт из списка, диск замолчит и LED погаснет ([support.apple.com][1], [apple.stackexchange.com][2]).
   *Если Finder показывает значок в сайдбаре, можно нажать ту же ⏏ там — это тот же вызов* ([support.apple.com][3]).

### 1.2 Terminal-способ

```bash
# узнать номер устройства
diskutil list
# допустим, это /dev/disk3
diskutil unmountDisk /dev/disk3      # если вдруг что-то успело смонтироваться
diskutil eject /dev/disk3            # снимает питание порта
```

`diskutil eject` удаляет устройство из шины (USB Device Remove), что обычно выключает двигатель диска ([ss64.com][4], [discussions.apple.com][5]).

> **Отличие `unmountDisk` vs `eject`**: первое лишь снимает ФС, второе дополнительно «де-конфигурирует» USB-устройство — после него появится характерный щелчок остановки шпинделя ([discussions.apple.com][5]).

### 1.3 Если том «занят»

Finder может ругаться, что диск используется. Закройте файлы/приложения или найдите процесс через `lsof +D /Volumes/…`; затем повторите `eject` ([support.apple.com][6], [eclecticlight.co][7]). В крайнем случае просто **Shut Down** — macOS автоматически размонтирует всё перед выключением ([support.apple.com][8]).

---

## 2 . Linux

### 2.1 Через GNOME Disks (или KDE Partition Manager)

* Выберите диск → шестерёнка → **Unmount** для каждого раздела, затем **Power Off**.
  Этот пункт вызывает те же методы udisks2, что и CLI ниже ([askubuntu.com][9], [unix.stackexchange.com][10]).

### 2.2 Командная строка (udisksctl)

```bash
# 1. Сбросить данные на диск
sync
# 2. Размонтировать все разделы (пример: диск /dev/sdb, раздел /dev/sdb1)
udisksctl unmount -b /dev/sdb1
# 3. Полностью обесточить устройство
udisksctl power-off -b /dev/sdb
```

`power-off` заставляет udisks2: (а) убедиться, что разделы не заняты; (б) выполнить `STOP UNIT`; (в) де-конфигурировать USB-контроллер — питание 5 V снимается, диск засыпает ([manpages.ubuntu.com][11], [reddit.com][12]).

### 2.3 Альтернативы

* Только «усыпить» диск без удаления устройства: `hdparm -Y /dev/sdb` ([superuser.com][13], [support.apple.com][14]).
* Полностью убрать устройство из системы (если udisksctl недоступен):

  ```bash
  echo 1 | sudo tee /sys/block/sdb/device/delete
  ```

  При повторном подключении ядро обнаружит диск заново ([superuser.com][15], [unix.stackexchange.com][10]).

---

## 3 . Экспресс-шпаргалка

| Цель                         | macOS                                   | Linux                                                   |
| ---------------------------- | --------------------------------------- | ------------------------------------------------------- |
| Размонтировать раздел        | `diskutil unmount /dev/disk3s1`         | `umount /dev/sdb1` или `udisksctl unmount -b /dev/sdb1` |
| Отключить питание устройства | `diskutil eject /dev/disk3`             | `udisksctl power-off -b /dev/sdb`                       |
| Проверить, что диск исчез    | `diskutil list` — нет /dev/disk3        | `lsblk` — нет /dev/sdb                                  |
| Если том «занят»             | `lsof +D /Volumes/…` → закрыть процессы | `lsof /dev/sdb1` → закрыть процессы                     |
| GUI-вариант                  | Disk Utility ⏏                          | GNOME Disks → Power Off                                 |

После того как `eject`/`power-off` сработал и диск остановился (LED погас, шпиндель не крутится), можно безопасно выдёргивать кабель или выключать док-станцию.

[1]: https://support.apple.com/guide/mac-help/connect-storage-devices-mac-mchl027f1d66/mac?utm_source=chatgpt.com "Connect and use other storage devices with Mac - Apple Support"
[2]: https://apple.stackexchange.com/questions/445648/spin-down-external-usb-hard-drive-before-removing?utm_source=chatgpt.com "Spin down external USB hard drive before removing - Ask Different"
[3]: https://support.apple.com/guide/mac-help/eject-cds-and-dvds-from-your-mac-mchl2f6b0645/mac?utm_source=chatgpt.com "Eject CDs and DVDs from your Mac - Apple Support"
[4]: https://ss64.com/mac/diskutil.html?utm_source=chatgpt.com "diskutil Man Page - macOS - SS64.com"
[5]: https://discussions.apple.com/thread/858571?utm_source=chatgpt.com "Difference between unmount and eject - Apple Support Communities"
[6]: https://support.apple.com/guide/mac-help/eject-a-disk-mac-app-mh27076/mac?utm_source=chatgpt.com "If you can't eject a disk on Mac because an app is using it"
[7]: https://eclecticlight.co/2021/09/02/what-to-do-when-a-volume-cant-be-ejected-or-unmounted/?utm_source=chatgpt.com "What to do when a volume can't be ejected or unmounted"
[8]: https://support.apple.com/guide/mac-help/eject-a-disk-mac-solutions-mchlp1285/mac?utm_source=chatgpt.com "If you can't eject a disk on Mac, try these solutions - Apple Support"
[9]: https://askubuntu.com/questions/1163119/how-to-power-down-external-drive-safely?utm_source=chatgpt.com "How to power down external drive safely - Ask Ubuntu"
[10]: https://unix.stackexchange.com/questions/444611/gracefully-shutting-down-usb-disk-drives-before-disconnect?utm_source=chatgpt.com "Gracefully shutting down USB disk drives before disconnect"
[11]: https://manpages.ubuntu.com/manpages/bionic/man1/udisksctl.1.html?utm_source=chatgpt.com "udisksctl - The udisks command line tool - Ubuntu Manpage"
[12]: https://www.reddit.com/r/linuxquestions/comments/r34j7j/running_udisksctl_poweroff_b_devsdx_disables_usb/?utm_source=chatgpt.com "Running \"udisksctl power-off -b /dev/sdx\" disables USB port for ..."
[13]: https://superuser.com/questions/295913/how-to-mount-and-unmount-hard-drives-under-windows-the-unix-way?utm_source=chatgpt.com "How to mount and unmount hard drives under Windows (the unix way)"
[14]: https://support.apple.com/en-mn/guide/mac-help/mh27077/mac?utm_source=chatgpt.com "If you can't eject a disk because another user is using it on Mac"
[15]: https://superuser.com/questions/1281162/why-does-udisksctl-command-on-my-machine-say-that-power-off-is-not-a-valid-optio?utm_source=chatgpt.com "Why does udisksctl command on my machine say that power-off is ..."
