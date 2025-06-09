```bash
rsync -aHAX --human-readable \
      --info=progress2,name0 --no-inc-recursive \
      --log-file=/tmp/rsync.log \
      --stats --partial --inplace \
      /media/ARCH20TB/20241022-backup/ \
      /backup22TB/media/2024/20241022-backup/
```
