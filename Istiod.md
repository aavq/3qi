Похоже, что Kiali не «видит» control-plane Istio, поэтому на Cluster Status пишет: istiod — Not found. Ниже — причины по убыванию вероятности и как быстро проверить/исправить.

⸻

1) Kiali больше не видит нужные namespaces (переход с accessible_namespaces на discovery_selectors)

Симптом. После апгрейда вы меняли настройки пространств (у вас был вопрос про accessible_namespaces: ["**"] → discovery_selectors). Если селекторы пустые/не попадают в istio-system, Kiali просто не будет наблюдать этот namespace — и «не найдёт» istiod.

Проверка

# Посмотреть текущую конфигурацию Kiali
kubectl -n <ns-kiali> get cm kiali -o yaml | yq '.data."config.yaml"'    # (или CR kiali.io)

Ищем блок:

deployment:
  accessible_namespaces: ...
  discovery_selectors: ...

Исправление (самое быстрое, как «раньше»):

deployment:
  accessible_namespaces:
    - "**"
# discovery_selectors лучше убрать вообще, если они не нужны

или, если хотите именно селекторы:

deployment:
  discovery_selectors:
    default:
      - matchLabels:
          kiali.io/member-of: mesh
# и промаркировать нужные ns:
kubectl label ns istio-system kiali.io/member-of=mesh --overwrite

Итог: после применения — перезапустить Kiali и обновить страницу.

⸻

2) Неверно указана control-plane namespace в конфиге Kiali

Симптом. Istiod живёт не в том ns, где его ищет Kiali.

Проверка

# где реально крутится istiod?
kubectl get deploy,pod -A | egrep -i 'istiod|pilot'

Исправление
В конфиге Kiali должен быть верный ns:

istio_namespace: istio-system               # замените, если у вас другой
istio_component_namespaces:
  istiod: istio-system                      # на всякий случай зафиксируйте явно


⸻

3) Метки у Deployment Istiod отличаются от ожидаемых

По умолчанию Kiali ищет компоненты по метке app=istiod. Если ваш дистрибутив ставит только app.kubernetes.io/name=istiod, Kiali может не распознать компонент.

Проверка

kubectl -n istio-system get deploy -l app=istiod
kubectl -n istio-system get deploy -l app.kubernetes.io/name=istiod

Исправления (любой из вариантов):
	•	Добавить недостающую метку на Deployment:

kubectl -n istio-system label deploy <имя-deploy> app=istiod --overwrite


	•	Или научить Kiali использовать другой ключ метки:

istio_labels:
  app_label_name: app.kubernetes.io/name
  version_label_name: app.kubernetes.io/version   # если у вас такая версия-метка



⸻

4) RBAC не даёт Kiali читать control-plane ns

Если при апгрейде вы ужесточили роли/констрейнты, Kiali может получать 403 на istio-system.

Проверка логов Kiali

kubectl -n <ns-kiali> logs deploy/kiali | egrep -i 'forbidden|permission|RBAC'

Исправление
Убедитесь, что ClusterRole/ClusterRoleBinding Kiali присутствуют и охватывают чтение по istio-system (deployments, pods, services, configmaps). Если используете Gatekeeper — проверьте, не блокирует ли он нужные правила.

⸻

5) Multi-cluster или «remote profile» без control-plane в этом кластере

Если это remote-кластер (только data-plane), а istiod крутится в другом кластере, в «Cluster Status» для данной записи будет «Not found».

Что делать
	•	Добавить в Kiali конфигурацию второго кластера, где реально крутится istiod, и включить multi-cluster режим (чтобы Kiali агрегировал статусы).
	•	Либо просто игнорировать «Not found» для remote-кластера и смотреть статус control-plane на «home»-кластере.

⸻

6) Istiod действительно не запущен/CrashLoop/Paused

Редко, но проверьте сам факт работы:

kubectl -n istio-system get deploy istiod* -o wide
kubectl -n istio-system get pods -l app=istiod -o wide

Починить по стандарту (ресурсы, вебхуки, CRD, ревизия, mTLS-политики).

⸻

Быстрый план действий (если нужно «прямо сейчас»)
	1.	Верните поведение «как раньше»:

deployment:
  accessible_namespaces: ["**"]

(и удалите discovery_selectors).

	2.	Убедитесь, что:

istio_namespace: istio-system
istio_component_namespaces:
  istiod: istio-system


	3.	Если меток app=istiod нет — либо добавьте их на Deployment, либо настройте istio_labels.app_label_name на app.kubernetes.io/name.

Если пришлёшь фрагмент твоего values.yaml/CR Kiali и вывод:

kubectl -n istio-system get deploy -o yaml | egrep -i 'name: istiod|labels:|app=|app.kubernetes.io/name'

— я точечно укажу, что именно поправить в твоей установке.
