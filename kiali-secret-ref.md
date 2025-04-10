Понимаю ваши сомнения относительно использования параметра `use_client_secret_from` в конфигурации Kiali для интеграции с OpenID Connect (OIDC). На текущий момент, согласно официальной документации и обсуждениям в сообществе разработчиков Kiali, **такой параметр отсутствует**.

Вместо этого, для безопасного хранения и использования `client_secret`, рекомендуется использовать **Kubernetes Secret** и передавать его в Kiali через переменные окружения. Этот метод подробно описан в официальной документации Kiali citeturn0search2.

**Пример:**

1. **Создание Kubernetes Secret:**

   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: kiali-oidc-secret
     namespace: istio-system
   type: Opaque
   data:
     client_id: <base64-encoded-client-id>
     client_secret: <base64-encoded-client-secret>
   ```


   Здесь значения `client_id` и `client_secret` должны быть закодированы в base64.

2. **Обновление Deployment Kiali для использования Secret:**

   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: kiali
     namespace: istio-system
   spec:
     template:
       spec:
         containers:
           - name: kiali
             env:
               - name: KIALI_AUTH_STRATEGY
                 value: "openid"
               - name: KIALI_OPENID_CLIENT_ID
                 valueFrom:
                   secretKeyRef:
                     name: kiali-oidc-secret
                     key: client_id
               - name: KIALI_OPENID_CLIENT_SECRET
                 valueFrom:
                   secretKeyRef:
                     name: kiali-oidc-secret
                     key: client_secret
   ```


Этот подход обеспечивает безопасное хранение чувствительных данных и их передачу в приложение.

Если вы используете Helm для установки Kiali, рекомендуется следовать официальным инструкциям по установке через Helm citeturn0search0.

Если у вас возникнут дополнительные вопросы или потребуется помощь с настройкой, рекомендую обратиться к официальной документации Kiali или сообществу разработчиков для получения наиболее актуальной информации. 
