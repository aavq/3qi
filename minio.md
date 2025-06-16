## Краткое резюме

Ошибка `‘server /data —console-address :9090’ is not a minio sub-command` говорит о том, что MinIO получает **одним-единственным аргументом** всю строку `server /data —console-address :9090`.
Причины бывают две:

1. В манифесте Kubernetes (или в Docker CMD/ENTRYPOINT) эта строка передана как **одна строка**, а не как набор отдельных аргументов («`server`», «`/data`», «`--console-address`», «`:9090`») ([stackoverflow.com][1], [github.com][2])
2. Использовано типографское длинное тире **«—»** вместо двух обычных дефисов **`--`** перед `console-address`, поэтому MinIO даже не распознаёт флаг ([github.com][3])

Ниже показано, как правильно задать команду и флаги, а также как отлаживать и избежать типичных ловушек.

---

## Почему MinIO ругается именно так

* CLI MinIO ждёт подкоманду (`server`, `gateway`, `mc`, …) первым позиционным аргументом.
  Если в аргументы попадает строка с пробелами, он считает её «неизвестной подкомандой» и выводит ровно это сообщение ([min.io][4])
* Точка входа в контейнере `minio/minio` уже прописана как `ENTRYPOINT ["minio"]`; следовательно, всё, что вы передаёте в Kubernetes **в поле `args`**, попадает именно в CLI MinIO ([stackoverflow.com][1])
* Флаг `--console-address` (документация называет его «static console port») задаёт порт консоли; при отсутствии флага порт выбирается случайно — с этим сложно работать за ингрессом или Service-ом ([min.io][5], [min.io][4])

---

## Правильный манифест Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
        - name: minio
          image: minio/minio:RELEASE.2025-05-24T17-08-30Z
          # EntryPoint уже "minio", поэтому достаточно args
          args:
            - server          # подкоманда
            - /data           # каталог данных
            - --console-address
            - ":9090"         # статический порт консоли
            - --address
            - ":9000"         # порт API (по желанию)
          env:
            - name: MINIO_ROOT_USER
              value: "minioadmin"
            - name: MINIO_ROOT_PASSWORD
              value: "StrongSecret123"
          ports:
            - containerPort: 9000
            - containerPort: 9090
```

* Делите **каждый** токен на отдельный элемент списка в `args` — именно так советуют и документация MinIO, и примеры на Stack Overflow фокусирующиеся на доступе к консоли ([stackoverflow.com][6], [stackoverflow.com][7])
* Если вам удобнее полностью переопределить `command`, можно написать `command: ["minio"]` и оставить тот же набор `args`.
* Флаги допустимо передавать через переменную-обёртку `MINIO_OPTS` — это эквивалентно CLI-аргументам ([min.io][4])

---

## Распространённые ошибки и как их проверить

| Симптом                                                           | Проверка                                                                                                                       | Исправление                                                                                          |                                                            |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| В логах: `‘server /data …’ is not a minio sub-command`            | \`kubectl logs POD                                                                                                             | head -n 20\`                                                                                         | Убедитесь, что `args` разделены, а флаги начинаются с `--` |
| Появляется `‘--console-address :9090’ is not a minio sub-command` | Посмотрите, нет ли кавычек вокруг всей строки в манифесте                                                                      | Разбейте на список, как в примере выше                                                               |                                                            |
| Консоль открывается на случайном порту (30 xxx)                   | В логе MinIO ищите строку `Console: http://127.0.0.1:41 987`                                                                   | Добавьте `--console-address ":9090"` и откройте порт 9090 в Service/Ingress ([stackoverflow.com][8]) |                                                            |
| Service не отвечает на `9000` или `9090`                          | `kubectl get svc minio -o yaml` → проверьте блок `ports`                                                                       | Убедитесь, что `targetPort` совпадает с `containerPort` ([stackoverflow.com][7])                     |                                                            |
| Вы используете MinIO Operator                                     | Operator генерирует Tenant со списком `args`, см. пример в README оператора ([github.com][9]) и в быстром гайде ([dev.to][10]) |                                                                                                      |                                                            |

---

## Полезные приёмы отладки

1. **Проверка entrypoint**:

   ```bash
   docker inspect --format '{{json .Config.Entrypoint}}' minio/minio
   ```

   убедитесь, что это действительно `["minio"]`.
2. **Временный запуск с `/bin/sh`**:

   ```yaml
   command: ["/bin/sh","-c"]
   args:
     - "exec minio server /data --console-address :9090"
   ```

   Подходит, если нужно быстро проверить флаги без правки списка аргументов.
3. **Используйте `kubectl exec`**, чтобы внутри Pods посмотреть, какие переменные окружения действительно установлены.

---

## Итоги и рекомендации

* **Разбивайте** команду MinIO на отдельные аргументы; не помещайте всё в одну строку.
* Всегда используйте двойной дефис `--` в флагах; случайно вставленное длинное тире «—» делает аргумент невалидным.
* Для консоли зафиксируйте порт флагом `--console-address` и откройте его в Service/Ingress. Это избавит от переадресации на случайный порт, о которой MinIO честно предупреждает ([min.io][5])
* Если позже перейдёте на MinIO Operator либо Helm-чарт, сохраните тот же набор `args` — структура та же, меняется лишь способ доставки манифеста ([min.io][11], [min.io][12])

Следуя этим шагам вы избавитесь от ошибки «not a minio sub-command» и получите рабочий MinIO, доступный на `http://<node|Ingress>:9000` (S3 API) и `http://<node|Ingress>:9090` (веб-консоль). Удачной эксплуатации!

[1]: https://stackoverflow.com/questions/46334551/heroku-deploying-minio-server-with-dockerfile-cmd-failure "docker - Heroku: deploying minio server with Dockerfile CMD failure - Stack Overflow"
[2]: https://github.com/minio/minio/issues/20804 "it is not possible to change API and console port inside docker env · Issue #20804 · minio/minio · GitHub"
[3]: https://github.com/medusajs/medusa/issues/3957 "miniIO related documentation contains an error · Issue #3957 · medusajs/medusa · GitHub"
[4]: https://min.io/docs/minio/linux/reference/minio-server/minio-server.html "MinIO Server — MinIO Object Storage for Linux"
[5]: https://min.io/docs/minio/linux/administration/minio-console.html "MinIO Console — MinIO Object Storage for Linux"
[6]: https://stackoverflow.com/questions/70785172/k8s-deployment-minio-how-to-access-the-console?utm_source=chatgpt.com "K8s deployment Minio How to access the Console? - Stack Overflow"
[7]: https://stackoverflow.com/questions/74854998/how-to-access-a-minio-instance-within-a-kubernetes-cluster "web services - How to access a MinIO instance within a Kubernetes cluster? - Stack Overflow"
[8]: https://stackoverflow.com/questions/72781687/minio-deployment-in-kubernetes-console-getting-redirected "Minio Deployment in Kubernetes : Console getting redirected - Stack Overflow"
[9]: https://github.com/minio/operator "GitHub - minio/operator: Simple Kubernetes Operator for MinIO clusters :computer:"
[10]: https://dev.to/giveitatry/how-to-install-minio-in-kubernetes-in-15-min-47h9 "How to install MinIO in Kubernetes in 15 min. - DEV Community"
[11]: https://min.io/docs/minio/kubernetes/upstream/operations/installation.html?utm_source=chatgpt.com "Deploy the MinIO Operator — MinIO Object Storage for Kubernetes"
[12]: https://min.io/docs/minio/kubernetes/upstream/index.html?utm_source=chatgpt.com "MinIO Object Storage for Kubernetes"
