```bash
rhash -r --sha256 -P --speed -o ./20241022-backup.sha256 .
```

```bash
rsync -aHAX --human-readable \
      --info=progress2,name0 --no-inc-recursive \
      --log-file=/tmp/rsync.log \
      --stats --partial --inplace \
      /media/ARCH20TB/20241022-backup/ \
      /backup22TB/media/2024/20241022-backup/
```

```bash
rhash --check --skip-ok ./20241022-backup.sha256
```
