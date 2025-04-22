**TL;DR** — Оставить «чистый» Istio‑чарт, при этом добавлять EnvoyFilter и другие кастомные объекты можно как минимум пятью способами. Самые распространённые:  
* создать **umbrella‑чарт** с Istio в dependencies и своими шаблонами;  
* держать **отдельный Helm‑чарт**/приложение Argo CD для кастомных CRD и управлять порядком деплоя через *sync waves*;  
* использовать **post‑renderer (kustomize)** при `helm template|install`, что умеет и Argo CD;  
* прибегнуть к **Argo CD Multiple Sources** (Helm + Kustomize overlay в одном Application);  
* управлять всем через **IstioOperator** и описывать EnvoyFilter как *overlay*.  
Ниже ‑ детали, плюсы/минусы и рабочие примеры.  

---

## 1  Отдельный Helm‑чарт/приложение для кастомных ресурсов  

### Идея  
*Istio* ставится как есть, а EnvoyFilter, VirtualService и т.д. находятся в маленьком чарте `istio‑custom`, на который указывает **второе Argo CD Application** либо второй источник того же Application citeturn0search4.  
```bash
helm upgrade --install istio-custom ./istio-custom -n istio-system
```  

### Управление порядком  
Помечаем все манифесты чарта волной `1` — тогда Argo CD синхронизирует их **после** объектов из Istio‑релиза (волна `0`) citeturn0search19turn0search0.  
```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"
```  

### Плюсы  
* полный decoupling — обновления Istio не затрагивают кастомный чарт;  
* тот же workflow «один чарт = один релиз»;  
* легко применить в существующем Git‑репозитории (новая папка + `App`).  

### Минусы  
* нужно следить за зависимостью (EnvoyFilter должен появиться **после** шлюза);  
* две точки отслеживания версий/хэшей вместо одной.

---

## 2  Umbrella‑чарт с Istio в dependencies  

### Концепция  
Создаём пустой чарт `my‑istio`, а в `Chart.yaml` описываем зависимости:  
```yaml
dependencies:
  - name: base
    version: ~1.25.2
    repository: https://istio-release.storage.googleapis.com/charts
  - name: gateway
    version: ~1.25.2
    repository: https://istio-release.storage.googleapis.com/charts
```  
citeturn0search5  

В `templates/` кладём любой YAML, например `envoyfilter‑ingressgw.yaml`:  
```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: custom‑ingress‑filter
spec:
  workloadSelector:
    labels:
      istio: ingressgateway
  # ...
```  

### Плюсы  
* весь стек — один Helm‑release и одно Argo CD Application;  
* version‑pinning через `Chart.lock`;  
* переход с Argo CD на `helm upgrade` и обратно — безболезнен.  

### Минусы  
* надо периодически обновлять `requirements.lock`/`Chart.lock`;  
* «толстый» diff при любой смене версии Istio;  
* невозможность выкатывать EnvoyFilter отдельно.

---

## 3  Helm post‑renderer + Kustomize  

### Механика  
Helm ≥ 3.1 позволяет «прогонять» результат рендеринга через внешний бинари:  
```bash
helm upgrade istio-base istio/base \
  --namespace istio-system \
  --post-renderer ./kustomize.sh
```  
Документация Helm приводит kustomize как canonical‑пример citeturn0search7; практический пример скрипта — gist citeturn0search2.  

`kustomization.yaml` может просто добавлять ваш EnvoyFilter:  
```yaml
resources:
  - envoyfilter.yaml
patchesStrategicMerge: []
```  

### Плюсы  
* upstream‑чарт остаётся неизменным;  
* патчи лежат рядом с кодом, не мешая Helm‑values;  
* хорошо сочетается с Argo CD, которое имеет встроенную поддержку пост‑рендереров.  

### Минусы  
* нужен общий runtime (kustomize CLI) в CI и в Argo CD; при рассинхроне результатов возможен «drift» citeturn0search7;  
* diff в Argo CD сложнее читать — виден итог после патча.

---

## 4  Argo CD Multiple Sources (Helm + Kustomize overlay)  

Argo CD 2.7+ позволяет объявить в одном `Application` сразу **два источника**:  
* `source[0]` — Helm‑чарт Istio;  
* `source[1]` — директория с Kustomize, где лежит `envoyfilter.yaml`.  

Последний источник «побеждает» при коллизии ресурсов, что даёт чистый способ оверрайдить объекты без fork‑чарта citeturn0search4.  

### Плюсы  
* один объект `Application`;  
* четко видно, где именно живут оверлеи;  
* можно использовать как Helm‑values, так и kustomize‑патчи.  

### Минусы  
* поддержка multiple‑sources пока не все плагины/UX‑инструменты Argo знали до конца;  
* при ошибке патча Argo CD выкинет `RepeatedResourceWarning`.

---

## 5  IstioOperator с overlay‑EnvoyFilter  

Вместо Helm‑чартов Istio можно установить **IstioOperator CR**; в поле `components.ingressGateways[].k8s.overlays` описать EnvoyFilter прямо внутри одной декларации citeturn0search3turn0search8.  

### Пример  
```yaml
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: istio
spec:
  profile: default
  components:
    ingressGateways:
    - name: istio-ingressgateway
      enabled: true
      k8s:
        overlays:
        - kind: EnvoyFilter
          name: custom-ingress-filter
          patches:
          - path: spec.workloadSelector.labels.istio
            value: ingressgateway
```  

### Плюсы  
* один CR описывает и контрольную плоскость, и все оверлеи;  
* честная API Istio (без Helm‑обёртки);  
* удобная миграция между версиями через `istioctl install -f`.  

### Минусы  
* переход с Helm → Operator меняет pipeline;  
* в Argo CD нужно заменить источник с Helm на plain‑YAML/`kustomize`.

---

## Что выбрать?  

| Подход | Когда брать | Главный + | Главный − |
|-------|-------------|-----------|-----------|
| **Отдельный чарт / App** | Уже есть Git‑репо под Istio‑чарт и нужен минимальный change‑set. | Независимые релизы; простейшая реализация. | Требуется sync‑ordering. |
| **Umbrella‑чарт** | Хотите «один релиз = вся Istio‑платформа». | Сквозной version‑lock; единый Helm diff. | Обновлять deps руками; большие диффы. |
| **Post‑renderer** | Любите Helm, но нужны точечные патчи. | Upstream не форкается; патчи рядом. | Нужен kustomize runtime; сложный diff. |
| **Multiple Sources** | Предпочитаете минимум Chart‑кода, максимум Git‑Ops. | Один `Application`; Helm+patches в одном месте. | Фича свежая, не все тулзы поддерживают. |
| **IstioOperator** | Готовы уйти от Helm entirely. | Нативная Istio API; overlays first‑class. | Требуется миграция pipeline. |

---

### Полезные ссылки  

* EnvoyFilter docs citeturn0search1, примеры citeturn0search6  
* Helm post‑renderer gist citeturn0search2, официальный гайд citeturn0search7  
* Argo CD Multiple Sources citeturn0search4  
* Sync waves citeturn0search19  
* Helm umbrella overview citeturn0search5  
* Blog о post‑renderer citeturn0search16  
* IstioOperator reference citeturn0search3  
* GitHub issue с overlay‑примерами citeturn0search8  
* Пример EnvoyFilter в Helm‑чарте citeturn0search20  

Эти варианты покрывают большинство сценариев, встречающихся у команд GitOps/Argo CD. Выберите тот, который лучше вписывается в ваш процесс обновления Istio и балансирует между гибкостью и простотой поддержки.
