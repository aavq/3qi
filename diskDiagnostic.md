**Кратко**: Для exFAT‑форматирования на Raspberry Pi достаточно установить пакет `exfatprogs`, создать (или заново разметить) раздел, выполнить `mkfs.exfat`, а затем проверять файловую систему `fsck.exfat`. Для диагностики самой флэш‑памяти удобно комбинировать несколько инструментов:  

| Цель | Утилита | Пакет | Разрушающая? | Ключевые команды |
|------|---------|-------|--------------|------------------|
| Проверка заявленного объёма/перепрошитых ячеек | **F³ (f3probe / f3write‑read)** | `f3` | *может стирать* | `sudo f3probe --destructive /dev/sdX`<br>`f3write /mnt/usb && f3read /mnt/usb` |
| Поиск сбойных блоков | **badblocks** | `util-linux` | *да* (режим ‑w) | `sudo badblocks -wsv -b4096 /dev/sdX` |
| Проверка/исправление exFAT | **fsck.exfat** | `exfatprogs` | нет | `sudo fsck.exfat -v /dev/sdX1` |
| Анализ контроллера (erase block / page) | **flashbench** | `flashbench` (из GitHub) | нет | `sudo flashbench -a /dev/sdX` |
| Производительность (последоват. и случ. I/O) | **hdparm**, **fio**, **dd** | `hdparm`, `fio`, `coreutils` | нет | `hdparm -Tt /dev/sdX`<br>`fio --name=randrw …` |
| SMART‑статус (если контроллер даёт «SAT pass‑thru») | **smartctl** | `smartmontools` | нет | `smartctl -a -d sat /dev/sdX` |
| GUI‑тест скорости и SMART | **GNOME Disks** | `gnome-disk-utility` | нет | «Шестерёнка → Benchmark» |

---

## 1. Установка необходимого ПО

```bash
sudo apt update
sudo apt install exfatprogs f3 flashbench util-linux badblocks smartmontools hdparm fio gnome-disk-utility
```

*`exfatprogs` предоставляет `mkfs.exfat`, `fsck.exfat`, `tune.exfat` и другие утилиты citeturn0search0.*  
*`f3` проверяет реальную ёмкость флэш‑устройств citeturn0search1.*  
*`flashbench` позволяет изучить геометрию памяти citeturn3view0.*

---

## 2. Подготовка и форматирование в exFAT

1. **Выяснить имя устройства**  
   ```bash
   lsblk -o NAME,SIZE,MODEL,TRAN
   ```
2. **Размонтировать разделы**  
   ```bash
   sudo umount /dev/sdX?  # если система сама примонтировала
   ```
3. **(Необязательно) стереть прежние сигнатуры**  
   ```bash
   sudo wipefs -a /dev/sdX          # ⚠ стирает таблицу разделов citeturn1search1
   ```
4. **Разметить заново** — например, в `parted`  
   ```bash
   sudo parted /dev/sdX -- mklabel gpt
   sudo parted /dev/sdX -- mkpart primary 0% 100%
   ```
5. **Собственно форматирование**  
   ```bash
   sudo mkfs.exfat -n USB256 /dev/sdX1   # создаёт exFAT ФС citeturn1search4
   ```
6. **Проверка**  
   ```bash
   sudo fsck.exfat /dev/sdX1             # проверяет и пытается чинить citeturn0search8
   ```

На Raspberry Pi 5 поддержка exFAT доступна «из коробки» после установки `exfatprogs` citeturn0search7.

---

## 3. Диагностика самой флэш‑памяти

### 3.1 Проверить заявленный объём и «фальшивые» блоки (F³)

```bash
sudo f3probe --destructive --time-ops /dev/sdX      # Быстрый полный тест
# или, менее опасно:
sudo mount /dev/sdX1 /mnt/usb
f3write /mnt/usb && f3read /mnt/usb
```
`f3probe` выявит, нет ли «зеркальной» или «циклической» прошивки, урезающей реальный объём накопителя citeturn2view1.

### 3.2 Поиск аппаратных бэд‑блоков

```bash
sudo badblocks -wsv -b 4096 -o badblocks.log /dev/sdX
```
Режим `-w` перезаписывает устройство, поэтому **сотрёт все данные**; используйте его до создания разделов citeturn0search2.

### 3.3 Тестирование производительности

* **hdparm** для быстрой оценки последовательного чтения:  
  `sudo hdparm -Tt /dev/sdX` citeturn4view0  
* **fio** для моделирования реальной нагрузки (случайные I/O, разные размеры блоков):  
  ```bash
  fio --name=randrw --rw=randrw --bs=4k --size=1G --direct=1 \
      --numjobs=4 --filename=/dev/sdX
  ```  
  Подробную документацию см. citeturn0search6  
* **dd** для простого замера записи:  
  `dd if=/dev/zero of=/dev/sdX bs=1M status=progress`

### 3.4 Анализ контроллера – flashbench

```bash
sudo flashbench -a /dev/sdX
```
Утилита покажет предполагаемый размер страничек и erase‑блоков, что полезно при подборе размера кластера либо при тюнинге I/O citeturn3view0.

### 3.5 SMART‑информация

Многие флэшки не передают SMART, но если внутри контроллер с «SAT pass‑thru» (чаще в SSD‑коробочках), можно попробовать:

```bash
sudo smartctl -a -d sat /dev/sdX
```
Список поддерживаемых мостов смотрите на wiki smartmontools citeturn5view0.

### 3.6 Графический способ (GNOME Disks)

Пакет `gnome-disk-utility` даёт удобное окно, где доступны:  
* «SMART Data & Self‑Tests»  
* «Benchmark…» (читает/пишет и строит график) citeturn0search4turn6view0  

---

## 4. Практическая последовательность «с нуля»

```bash
# 0) убедитесь, что выбрали правильное устройство!
lsblk -o NAME,SIZE,MODEL

# 1) стереть сигнатуры и таблицу разделов (опционально)
sudo wipefs -a /dev/sdX

# 2) полный разрушающий тест badblocks (оставьте на ночь)
sudo badblocks -wsv -b4096 /dev/sdX

# 3) создать GPT и один раздел
sudo parted /dev/sdX -- mklabel gpt
sudo parted /dev/sdX -- mkpart primary 0% 100%

# 4) форматировать в exFAT
sudo mkfs.exfat -n USB256 /dev/sdX1

# 5) смонтировать и проверить полезную ёмкость (неразрушающе)
sudo mount /dev/sdX1 /mnt/usb
f3write /mnt/usb && f3read /mnt/usb
sudo umount /mnt/usb

# 6) финальная проверка ФС
sudo fsck.exfat -v /dev/sdX1
```

---

## 5. Совет по размеру кластера exFAT

* По умолчанию `mkfs.exfat` выбирает кластер автоматически, но для 256 ГБ флэш‑накопителя разумное значение — 128 КБ.  
* Пример: `mkfs.exfat -s 128K /dev/sdX1`.  
  (Классическая рекомендация SD Association см. в `man mkfs.exfat`) citeturn1search9.

---

### Полезные источники

* Debian package `exfatprogs` citeturn0search0  
* Debian package `f3` citeturn0search1  
* Руководство по exFAT на Raspberry Pi citeturn0search7  
* Статья о `badblocks` citeturn0search2  
* Обзор `fsck.exfat` citeturn0search8  
* Справка о `wipefs` citeturn1search1  
* fio documentation citeturn0search6  
* Практика замеров hdparm/dd/fio citeturn4view0  
* flashbench README citeturn3view0  
* Список поддерживаемых USB‑SMART мостов citeturn5view0  
* GNOME Disks benchmark citeturn0search4  

Эти инструменты позволяют полностью обследовать флэш‑накопитель (ёмкость, производительность, физические сбои и состояние ФС) без необходимости подключать его к Windows‑утилитам.

