### Что показывает скрин-лог

Kiali каждые несколько секунд пытается «list / watch» объекты, которых **нет** в вашем `ClusterRole`.
По-строчно из лога (читаем после слова *resource*):

| API Group                   | Resource                                            |
| --------------------------- | --------------------------------------------------- |
| `networking.istio.io`       | **workloadgroups**                                  |
| `gateway.networking.k8s.io` | **referencegrants**, **httproutes**, **grpcroutes** |
| `telemetry.istio.io`        | **telemetries**                                     |
| `extensions.istio.io`       | **wasmplugins**                                     |

Сервис-аккаунт `system:serviceaccount:kiali:kiali` не имеет `list/watch` на эти ресурсы, поэтому kube-api возвращает `Forbidden`, а Kiali пишет `Failed to list … is forbidden`.

Gatekeeper при этом **успешно пропустил** обновлённую роль — но она просто оказалась неполной.

---

## Шаг 1. Соберите список недостающих ресурсов «автоматически»

```bash
# (1) Сохраняем свежий лог
kubectl logs deploy/kiali -n kiali --since=5m > /tmp/kiali.log

# (2) Выдёргиваем уникальные пары "<apigroup> <resource>"
grep -oP 'resource\\s+"[^"]+"' /tmp/kiali.log \
| awk '{print $2}' | tr -d '"' \
| sort -u
```

У вас должно получиться нечто вроде:

```
grpcroutes
httproutes
referencegrants
telemetries
wasmplugins
workloadgroups
```

---

## Шаг 2. Дописываем `ClusterRole kiali-viewer`

> **Важно:** всё ещё без wildcard — это полностью удовлетворяет
> Gatekeeper-констрейнту **policy-essentials-v2022-prohibit-role-wildcard-access**.

```yaml
# kiali/overlays/rbac-fix/clusterrole-patch.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kiali-viewer
$patch: merge
rules:
# --- Istio networking (добавили workloadgroups) -------------
- apiGroups: ["networking.istio.io"]
  resources:
    - workloadgroups           # NEW
    - destinationrules
    - gateways
    - virtualservices
    - serviceentries
    - sidecars
    - envoyfilters
    - workloadentries
  verbs: ["get","list","watch"]

# --- Istio telemetry ----------------------------------------
- apiGroups: ["telemetry.istio.io"]
  resources:
    - telemetries              # NEW
  verbs: ["get","list","watch"]

# --- Istio Wasm plugins -------------------------------------
- apiGroups: ["extensions.istio.io"]
  resources:
    - wasmplugins              # NEW
  verbs: ["get","list","watch"]

# --- Kubernetes Gateway API objects -------------------------
- apiGroups: ["gateway.networking.k8s.io"]
  resources:
    - httproutes               # NEW
    - grpcroutes               # NEW
    - referencegrants          # NEW
  verbs: ["get","list","watch"]
```

Сохраняем, коммитим в Git-репо, запускаем **Sync** в Argo CD.

---

## Шаг 3. Проверяем

```bash
# Pod должен перезапуститься (Argo или вручную)
kubectl rollout restart deploy/kiali -n kiali

# Через минуту смотрим, остались ли Forbidden
kubectl logs deploy/kiali -n kiali --since=2m | grep -i "is forbidden" || echo "Нет ошибок RBAC 🎉"
```

Если строк «is forbidden» больше нет — значит RBAC-прав хватило и Gatekeeper тоже доволен (ни одного wildcard’а).

---

## А если появятся новые `is forbidden`?

1. Повторите **Шаг 1** — иногда после устранения первой порции Kiali переходит к следующей.
2. Добавьте недостающие ресурсы в тот же patch-файл.

Набор CRD зависит от версии Istio / Gateway API; при апгрейде могут появляться новые типы (например `tlsroutes`, `tcproutes`).

---

## Альтернативные (но менее желательные) варианты

| Подход                                         | Что делать                                                                        | Комментарий                                              |
| ---------------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **Ослабить Gatekeeper только для этой роли**   | Добавить `spec.parameters.exemptions.clusterRoles: ["kiali-viewer"]` в Constraint | Самый быстрый, но политика для Kiali больше не действует |
| **Оставить wildcard, но только внутри группы** | Gatekeeper-шаблон не различает «scope» — любое `resources: ["*"]` запрещён        | Требуется менять Rego-шаблон: > 5-10 мин                 |
| **Label-исключение целого NS**                 | `kubectl label ns kiali admission.gatekeeper.sh/ignore=true`                      | Сбрасывает все политики Gatekeeper в namespace           |

---

### Итого

* Ошибки `cannot list resource … is forbidden` — это недостаточные RBAC.
* Gatekeeper больше не мешает; надо **дописать** отсутствующие ресурсы в `ClusterRole`.
* После добавления (`workloadgroups`, `telemetries`, `wasmplugins`, `httproutes`, `grpcroutes`, `referencegrants`) ошибки уходят, Kiali снова строит граф и метрики.
