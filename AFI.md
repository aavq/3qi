Коротко: самый простой и «точный» способ — задать nodeAffinity с исключением (NotIn) по стандартной метке узла kubernetes.io/hostname. Тогда Pod никогда не уедет на этот Node.

Вариант 1 (рекомендую): nodeAffinity c NotIn
	1.	Узнай имя узла, которого нужно избежать:

kubectl get nodes -o custom-columns=NAME:.metadata.name,HOST:.metadata.labels['kubernetes\.io/hostname']

	2.	Добавь в Pod/Deployment/StatefulSet:

spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          # Жёсткое требование: не планировать на указанные ноды
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: kubernetes.io/hostname
                    operator: NotIn
                    values:
                      - node-to-avoid   # <- имя узла из шага 1

Поведение: если единственные доступные ноды — запрещённые, Pod останется Pending (что и нужно, чтобы он не попал туда).

Вариант 2: своя метка на «плохом» узле + DoesNotExist

Подходит, если хочешь пометить любой узел как «запрещённый», не перечисляя хостнеймы.
	1.	Пометь узел:

kubectl label node node-to-avoid avoid-me=true

	2.	В манифесте Pod:

spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: avoid-me
                    operator: DoesNotExist

Логика: Pod будет планироваться только на узлы, где нет метки avoid-me. Любые узлы с avoid-me=true исключаются.

Вариант 3: выбрать «разрешённые» узлы (white-list)

Если «запрещённых» мало, а «разрешённых» — конкретный пул:

# Проставь метку всем, куда МОЖНО
kubectl label node good-node-1 can-run=true
kubectl label node good-node-2 can-run=true

spec:
  template:
    spec:
      nodeSelector:
        can-run: "true"

Минус: новые узлы без метки не подойдут, пока не прометишь.

Вариант 4: taints/tolerations (кластерное ограждение)

Хочешь запретить почти всем Pod-ам попадать на узел:

kubectl taint nodes node-to-avoid dedicated=blocked:NoSchedule

Теперь:
	•	Любой Pod без toleration туда не попадёт.
	•	Те Pod-ы, которым можно, добавляют toleration:

tolerations:
  - key: "dedicated"
    operator: "Equal"
    value: "blocked"
    effect: "NoSchedule"



Минус: это затрагивает все ворклоады; для «одного конкретного Pod-а» обычно избыточно.

⸻

Полезные замечания
	•	requiredDuringSchedulingIgnoredDuringExecution — жёсткое правило при планировании; уже запущенные Pod-ы не выселяются, если метки/условия изменились.
	•	Для DaemonSet эти же поля (nodeSelector/affinity) работают: можно исключить конкретные узлы из развёртывания демонов.
	•	Если целишься по имени узла, kubernetes.io/hostname — стандартная и самая простая метка. Не путать с nodeName (он прибивает Pod к узлу, а не исключает).
	•	Проверка: после изменения манифеста делай kubectl apply --server-side --dry-run=server -f … и смотри kubectl describe pod … → раздел Events на предмет причин Unschedulable.

⸻

Мини-пример Deployment целиком

apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: kubernetes.io/hostname
                    operator: NotIn
                    values: ["node-to-avoid"]
      containers:
        - name: nginx
          image: nginx:1.27

Если опишешь свой кейс (один Pod или класс Pod-ов, временно/навсегда, есть ли автоскейлинг узлов), подскажу оптимальную стратегию (affinity vs taints) и дам готовые kubectl команды под твой CI/CD.
