Проблема, с которой вы столкнулись, выглядит так, что при установке Keycloak (с базой PostgreSQL от Bitnami) **не удаётся забиндить PVC (PersistentVolumeClaim)** из-за отсутствия или неправильной настройки **StorageClass** в вашем локальном кластере. В результате поды `keycloak-postgresql-0` и `keycloak-0` (который завязан на БД) не могут корректно стартовать.

Также `keycloak-0` выдаёт `Readiness probe failed` со статусом `500`, что часто происходит, когда Keycloak не может подключиться к БД (а БД не поднята из-за проблем с PVC).

Ниже — что можно предпринять:

---

## 1. Причина: «pod has unbound immediate PersistentVolumeClaims»

В вашем локальном кластере Kubernetes (Lima) по умолчанию обычно **нет** динамического провайдера хранилища (как в облаке). Следовательно:

- Helm-чарт Bitnami для Keycloak (и PostgreSQL) пытается создать **PersistentVolumeClaims**.
- Поды остаются в состоянии `Pending`, т.к. **PVC не биндится** к физическим или виртуальным дискам (нет StorageClass, который бы выдал автоматический PersistentVolume).
- Без доступной БД Keycloak не инициализируется и readiness-probe падает.

Для локального окружения можно решить двумя путями:

### 1.1. Установка локального StorageClass (например, Local Path Provisioner)

В Lima или других локальных кластерах (kind, minikube и т. п.) часто используют **Local Path Provisioner** от Rancher, который умеет автоматически создавать папки/volume на локальном диске VM и биндить PVC.

1. **Установите Local Path Provisioner**:
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml
   ```
2. **Сделайте его StorageClass по умолчанию** (если хотите):
   ```bash
   kubectl patch storageclass local-path \
     -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
   ```
3. **Убедитесь**:
   ```bash
   kubectl get storageclass
   ```
   Видите `local-path` со статусом `(default)`. Теперь любая PVC без явного `storageClassName` будет получать том в `/var/lib/rancher/...` внутри ноды.

4. После этого Helm-чарт сможет автоматически создать необходимые PersistentVolumes (через Local Path Provisioner). Перепробуйте установку:
   ```bash
   helm install keycloak bitnami/keycloak \
     --set auth.adminUser=admin \
     --set auth.adminPassword=admin \
     --namespace default
   ```

5. **Проверяйте**:
   ```bash
   kubectl get pods
   kubectl describe pvc
   kubectl describe pv
   ```
   Теперь PVC должны быть в статусе `Bound`, поды `keycloak-postgresql-0` и `keycloak-0` — в `Running` (после инициализации).

### 1.2. Отключить persistent volume и использовать «ephemeral» хранилище

Если вы **просто для демо** и не хотите хранить данные устойчиво, можно отключить persistency у PostgreSQL и Keycloak:

```bash
helm install keycloak bitnami/keycloak \
  --set postgresql.primary.persistence.enabled=false \
  --set persistence.enabled=false \
  --set auth.adminUser=admin \
  --set auth.adminPassword=admin \
  --namespace default
```

- Тогда Postgres будет работать «в памяти» (Docker volume внутри пода), и при каждом рестарте данные будут теряться.
- Но хотя бы не будет проблем с PVC.

---

## 2. Readiness probe failed (HTTP 500)

Сообщение:
```
Readiness probe failed: HTTP probe failed with statuscode: 500
```
возникает, когда Keycloak внутри контейнера отвечает с ошибкой на `/health` (или `/realms/master/.well-known/openid-configuration`). Чаще всего из-за того, что Keycloak:

1. Не может соединиться с базой.
2. В процессе инициализации.
3. Некорректно сконфигурирован.

Как только **PostgreSQL реально заработает** (исправится проблема с PVC), Keycloak сможет подняться до конца, и readiness-probe сменится на 200 OK.

---

## 3. Резюме: как правильно запустить Keycloak в локальном кластере

1. **Добавить динамический StorageClass** (Local Path Provisioner):
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/master/deploy/local-path-storage.yaml
   kubectl patch storageclass local-path \
     -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
   ```
2. **Установить Keycloak** (через Bitnami Helm-чарт):
   ```bash
   helm repo add bitnami https://charts.bitnami.com/bitnami
   helm repo update
   helm install keycloak bitnami/keycloak \
     --set auth.adminUser=admin \
     --set auth.adminPassword=admin \
     --namespace default
   ```
3. **Верифицировать**:
   ```bash
   kubectl get pods
   # Ожидаем keycloak-0, keycloak-postgresql-0 в Running
   ```
4. **Доступ** к Keycloak (через port-forward, NodePort, или Istio Gateway).

Если всё равно нужна только тестовая среда без постоянного хранения БД, можете **выключить persistence**:

```bash
helm install keycloak bitnami/keycloak \
  --set postgresql.primary.persistence.enabled=false \
  --set persistence.enabled=false \
  --set auth.adminUser=admin \
  --set auth.adminPassword=admin \
  --namespace default
```

Таким образом вы избежите проблем с PVC, но база будет терять данные при каждом рестарте подов.

---

## 4. После успешного запуска

Как только Keycloak-0 и keycloak-postgresql-0 будут `Running`, `kubectl describe pod` не будет показывать ошибки. Тогда:

1. **Port-forward** (для проверки UI):
   ```bash
   kubectl port-forward svc/keycloak 8080:8080
   ```
2. **Откройте** в браузере: http://localhost:8080/  
   Логин: `admin / admin`.  
   Увидите админ-консоль Keycloak.  

3. **Настройте Realm, Client** и т.д. (как обсуждалось ранее).

---

**Итог**: Основная загвоздка — отсутствие динамического провайдера хранилища, и потому `postgresql` не может получить том для хранения данных. Либо подключаем **Local Path Provisioner** (или другой StorageClass), либо отключаем persistency в Helm-чарте, если нужна только демоверсия без сохранения данных.
