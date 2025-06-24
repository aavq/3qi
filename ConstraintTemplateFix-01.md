Ниже — полный перевод предыдущего ответа на русский язык (с добавлением ссылок на документацию и issue-трекеры, подтверждающих каждое ключевое утверждение).

---

## Краткое содержание

Ошибка **«resource not found in cluster»** возникает, когда вы создаёте `Constraint`
раньше, чем Kubernetes API-сервер успевает зарегистрировать CRD,
который автоматически генерируется контроллером Gatekeeper из `ConstraintTemplate`.
Надо либо дождаться готовности шаблона (`kubectl wait …`), либо обеспечить
правильный порядок синхронизации в Helm/Argo CD. ([projectcontour.io][1], [dustinspecker.com][2])

---

## Что происходит под капотом

### 1. Асинхронная цепочка

1. **`kubectl apply` шаблона**
   Записывает объект `ConstraintTemplate` в etcd — на этом этапе нового
   API-ресурса ещё нет. ([open-policy-agent.github.io][3])
2. **gatekeeper-controller**
   Считывает шаблон и **создаёт CRD**
   `k8stenantwildcardhosts.constraints.gatekeeper.sh`. ([developers.redhat.com][4])
3. **API-сервер публикует CRD**
   Только после установки условий `Established=True`, `NamesAccepted=True`
   новый тип становится доступен клиентам. ([github.com][5])
4. Если в этом «окне» отправить `Constraint`, API вернёт
   «the server could not find the requested resource». ([github.com][6])

### 2. Статус шаблона

Gatekeeper пишет `.status.created: true`, когда CRD
уже зарегистрирован на всех репликах контроллера, что можно использовать
для ожидания готовности. ([github.com][7])

---

## Как убедиться, что всё готово

```bash
# Шаблон существует?
kubectl get constrainttemplates k8stenantwildcardhost -o wide

# CRD появился и установлен?
kubectl get crd k8stenantwildcardhosts.constraints.gatekeeper.sh

# Шаблон помечен как созданный (created=true)?
kubectl get constrainttemplates k8stenantwildcardhost \
  -o jsonpath='{.status.created}'
```

Команды показывают, прошли ли шаги 2–3. ([github.com][8], [github.com][9])

---

## Надёжные способы применения

### 1. Двухфазный `kubectl`

```bash
kubectl apply -f k8stenantwildcardhost-template.yaml
kubectl wait --for=condition=Ready \
  constrainttemplate/k8stenantwildcardhost --timeout=60s
kubectl apply -f k8stenantwildcardhost-constraint.yaml
```

`kubectl wait` гарантирует, что CRD уже зарегистрирован. ([github.com][8])

### 2. Helm / Kustomize / Argo CD

| Инструмент    | Что сделать                                                                                                                                            |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Helm**      | Вынести шаблоны в chart-CRDs или задать hook `"crd-install"`; Constraint-ы разместить в поздней «волне» (`helm.sh/hook-weight`). ([pradeepl.com][10])  |
| **Argo CD**   | Добавить аннотацию `argocd.argoproj.io/sync-wave` (шаблон = -1, Constraint = 0) или включить `syncOptions: - CreateNamespace=true`. ([github.com][11]) |
| **Kustomize** | Разбить на два слоя (base/overlays) и применять последовательно.                                                                                       |

### 3. Config Sync / ACM

В Anthos Config Sync шаблон и Constraint можно
коммитить в один каталог — reconciler автоматически ретраит,
пока CRD не появится. ([cloud.google.com][12])

---

## Частые проблемы и их решения

| Симптом                                      | Причина                                                                                                             | Решение                                                                          |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Ошибка остаётся спустя минуты                | ServiceAccount Gatekeeper не имеет `cluster-admin` (не может создать CRD)                                           | Добавить `ClusterRoleBinding` с `cluster-admin`. ([medium.com][13])              |
| `kubectl apply` на Constraint всё ещё падает | `apiVersion` Constraint-а не совпадает с поддерживаемой (нужно `constraints.gatekeeper.sh/v1beta1` для Anthos 1.20) | Исправить `apiVersion`. ([pradeepl.com][10])                                     |
| Constraint допускает всё                     | `kind` в ConstraintTemplate («K8sTenantWildcardHost») отличается от `kind` Constraint-а («k8st...host»)             | Сделать названия идентичными, учесть регистр. ([open-policy-agent.github.io][3]) |

---

## TL;DR

* **Шаблон → ожидание → Constraint.**
* Проверяйте наличие CRD `k8stenantwildcardhosts.constraints.gatekeeper.sh`.
* Автоматизируйте ожидание с `kubectl wait`, Helm-хук-ами или sync-wave в Argo CD.
  После этого ошибка «resource not found» исчезнет, и политика начнёт защищать ваши Istio Gateway-и.

[1]: https://projectcontour.io/docs/1.30/guides/gatekeeper/?utm_source=chatgpt.com "Using Gatekeeper as a validating admission controller with Contour"
[2]: https://dustinspecker.com/posts/open-policy-agent-introduction-gatekeeper/?utm_source=chatgpt.com "Open Policy Agent: Introduction to Gatekeeper | Dustin Specker"
[3]: https://open-policy-agent.github.io/gatekeeper/website/docs/v3.13.x/constrainttemplates/?utm_source=chatgpt.com "Constraint Templates | Gatekeeper - GitHub Pages"
[4]: https://developers.redhat.com/articles/2024/05/03/simplify-gatekeeper-installation-and-constraint-management?utm_source=chatgpt.com "Simplify Gatekeeper installation and constraint management"
[5]: https://github.com/open-policy-agent/gatekeeper/issues/677?utm_source=chatgpt.com "CRDs for Constraints and ConstraintTemplates should have ..."
[6]: https://github.com/open-policy-agent/gatekeeper/issues/2129?utm_source=chatgpt.com "missing ConstraintTemplate when adding constraints #2129 - GitHub"
[7]: https://github.com/open-policy-agent/gatekeeper/issues/1499?utm_source=chatgpt.com "No automated way to wait on constraint template CRD upgrades ..."
[8]: https://github.com/open-policy-agent/gatekeeper/issues/1147?utm_source=chatgpt.com "'nonstructuralschema' prevent to wait for ConstraintTemplates CRD ..."
[9]: https://github.com/open-policy-agent/gatekeeper/blob/master/pkg/controller/constrainttemplate/constrainttemplate_controller_test.go?utm_source=chatgpt.com "constrainttemplate_controller_test.go - GitHub"
[10]: https://pradeepl.com/blog/kubernetes/deploying-gatekeeper-and-defining-constraints/?utm_source=chatgpt.com "Deploying OPA Gatekeeper and defining constraints"
[11]: https://github.com/argoproj/argo-cd/issues/9252?utm_source=chatgpt.com "Sync failed when deploy Gatekeeper ConstraintTemplate ... - GitHub"
[12]: https://cloud.google.com/kubernetes-engine/enterprise/policy-controller/docs/latest/reference/constraint-template-library?utm_source=chatgpt.com "Constraint template library | Policy Controller - Google Cloud"
[13]: https://medium.com/nerd-for-tech/opa-gatekeeper-on-kubernetes-69ca657c8631?utm_source=chatgpt.com "OPA Gatekeeper on Kubernetes - Medium"
