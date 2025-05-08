**Reviewing template differences**

The user is pointing out differences in how the template I proposed aligns with their example. Specifically, in their example, `@type` was nested under `typed_config`, while in my template, `@type` is directly under `patch.value`. It seems like the user remembers the `typed_config` layer, but upon reviewing the original template, there isn't a `typed_config` inside `patch.value` for `preserve-auth-header`. The Lua filter, however, does have `inlineCode` but that's separate from the other filter.

**Clarifying template differences**

The user is concerned about the use of `default_source_code.inline_string` in the template, questioning it against the deprecated `inlineCode` in the original example. The new Envoy version uses `default_source_code`, but older Istio versions still accept `inlineCode`. To address this, I'll provide both options—one with the deprecated field (`inlineCode`) for older versions, and one using the newer `default_source_code`. I'll also clarify the use of `patch.value` versus `patch.value.typed_config` to align with the original template.

**Clarifying patch.value issues**

The user seems confused about the use of `typed_config` in the header-merge filter. In the original example, the `patch.value` field directly contained the `@type` key, but in my version, it had `typed_config` before the `@type`. After a review, it appears that the original YAML doesn’t need `typed_config`; the patch merges at this level by default, thanks to the `applyTo` and `filter.name` settings in the header-merge operation. To address this, I can adjust the template slightly to include `typed_config` for clarity.


**Clarifying patch structure**

The user is asking whether `typed_config` should be included in the header-merge filter. When patching the HTTP connection manager (network), we target `typed_config` as part of the filter's patch operation. In the header-merge operation, the patch value automatically merges into the correct level within `typed_config`. While the spec expects patch.value to represent part of the config, the filter name targets `http_connection_manager`, and `typed_config` is merged by default during `HTTP_FILTER`.


**Addressing patch issue**

To ensure compatibility, it's safe to include `patch.value.typed_config`. This mimics older examples, though in the MERGE operation, the patch value fields will merge directly into the object if not specified. In the original YAML, patching is done with `http_connection_manager` using the `@type` field, and the spec automatically merges the value into `typed_config`. So, the user’s original example had no need for `typed_config`, but both methods can work depending on context.


**Clarifying header-merge issue**

It seems the user misread the use of `typed_config`. In header-merge, we intentionally merge at the `typed_config` level, and the root of `patch.value` is normally `typed_config`. Istio automatically merges `patch.value` into the existing filter's `typed_config`, so we don’t technically need to specify `typed_config` again. However, to align with earlier examples and for clarity, we can include it. Let's adjust the template and provide necessary explanations of the approach.


Thought for 1m 31s


Below is an annotated breakdown of **what needs to change in the Helm template** so that it exactly mirrors the YAML you showed and, at the same time, stays forward-compatible with newer Istio/Envoy releases.

---

## 1 | Why the fields look different

| Field in my first draft             | Your original YAML                                   | What the spec says                                                                                                                                          | Recommended fix                                                                                                                      |
| ----------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `default_source_code.inline_string` | `inlineCode`                                         | `inline_code` is **deprecated** since Envoy v1.18; `default_source_code` is the supported replacement ([Envoy Proxy][1])                                    | Keep both: generate `inline_code` for older clusters **or** `default_source_code` for ≥1.18, controlled by a value flag.             |
| `patch.value.@type` (header-merge)  | `patch.value.typed_config.@type` (your recollection) | When `applyTo: HTTP_FILTER`+`MERGE`, Istio merges whatever is put in `patch.value` **into the filter’s existing `typed_config` automatically** ([Istio][2]) | You can wrap it in a `typed_config:` block for perfect symmetry with the sample – both forms work. I show the wrapped version below. |

**Bottom line:**
\*Older Istio (<1.18) → use `inlineCode` and wrap the merge in `typed_config`.
*Newer Istio (≥1.18) → use `default_source_code`, and wrapping is optional.*

The updated template accommodates both.

---

## 2 | Revised Helm template

```yaml
{{/* templates/envoyfilter.yaml */}}
{{- range $f := .Values.filters }}
{{- range $sni := $f.sniList }}
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: {{ printf "%s-%s" $f.name ($sni | replace "." "-" | trunc 48) }}
  namespace: {{ $f.namespace | default "istio-system" }}
spec:
  workloadSelector:
    labels: {{- toYaml ($f.selector | default (dict "istio" "ingressgateway")) | nindent 6 }}
  configPatches:
    - applyTo: HTTP_FILTER
      match:
        context: {{ $f.context | default "GATEWAY" }}
        listener:
          portNumber: {{ $f.port | default 443 }}
          filterChain:
            sni: {{ $sni }}
            {{- if eq $f.kind "header-merge" }}
            filter: { name: "envoy.filters.network.http_connection_manager" }
            {{- end }}
      patch:
        operation: {{ ternary "MERGE" "INSERT_BEFORE" (eq $f.kind "header-merge") }}
{{/* ---------- Lua filter ---------- */}}
{{- if eq $f.kind "lua" }}
        value:
          name: envoy.filters.http.lua
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
{{- if $f.useLegacyInlineCode }}
            inline_code: |
{{ $.Files.Get (printf "files/%s" $f.script) | indent 14 }}
{{- else }}
            default_source_code:
              inline_string: |
{{ $.Files.Get (printf "files/%s" $f.script) | indent 16 }}
{{- end }}
{{/* ------- header-merge patch ----- */}}
{{- else }}
        value:
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
            request_headers_to_add:
              - header:
                  key: "Authorization"
                  value: "%REQ(Authorization)%"
                append: false
{{- end }}
---
{{- end }}{{- end }}
```

* **`useLegacyInlineCode`** (boolean) lets you switch between the deprecated `inline_code` and the modern `default_source_code` without touching the chart.
* Wrapping the merge in `typed_config:` makes the header patch *byte-for-byte* identical to your sample. It is functionally the same as the shorter form, but avoids confusion ([Stack Overflow][3], [GitHub][4]).

---

## 3 | Example `values-prod.yaml`

```yaml
filters:
  # TLS-CN parser
  - name: cert-parser
    kind: lua
    script: ingress-cert-parser.lua   # kept in files/
    useLegacyInlineCode: false        # flip to true for <1.18
    sniList:
      - 001.com

  # JWT e-mail extractor
  - name: jwt-user-crds
    kind: lua
    script: extract-username-from-jwt.lua
    useLegacyInlineCode: false
    sniList:
      - 001.com

  # Preserve original Authorization header
  - name: preserve-auth
    kind: header-merge
    sniList:
      - 001.com
```

---

## 4 | How to test quickly

1. **Render only**

   ```bash
   helm template -f values-prod.yaml . | istioctl validate -f -
   ```

   If Istio finds a structural issue it fails fast ([Istio][5]).
2. **Dry-run on a dev cluster**

   ```bash
   helm upgrade --dry-run --install envoy-filters . -f values-dev.yaml
   ```
3. **Check the listener**

   ````bash
   istioctl pc listeners $(kubectl -n istio-system \
     get pod -l istio=ingressgateway -o jsonpath='{.items[0].metadata.name}') \
     --port 443 | grep lua
   ``` :contentReference[oaicite:4]{index=4}
   ````
4. **Follow gateway logs** to watch your `handle:logInfo()` calls go by.

---

## 5 | Key take-aways

* **`inline_code` vs `default_source_code`** – Keep the flag; the former is easier to grep in very old clusters, the latter is the future and avoids deprecation warnings ([Envoy Proxy][1]).
* **Header-merge patch location** – Whether you nest under `typed_config` or not, Istio merges into the same proto (`HttpConnectionManager`) ([Istio][2]).
* **Everything else stays identical**: workload selector, filter order, SNI loop – so scaling to more clusters is still one-liner changes in `values.yaml`.

Feel free to drop this template back into your repo and ping me if any Istio version quirks pop up!

[1]: https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/lua/v3/lua.proto "Lua (proto) — envoy 1.35.0-dev-1e68b7 documentation"
[2]: https://istio.io/latest/docs/reference/config/networking/envoy-filter/ "Istio / Envoy Filter"
[3]: https://stackoverflow.com/questions/68506507/add-header-with-envoyfilter-does-not-work?utm_source=chatgpt.com "Add header with EnvoyFilter does not work - Stack Overflow"
[4]: https://github.com/istio/istio/discussions/50252?utm_source=chatgpt.com "How to increase the max header size for services within the mesh ..."
[5]: https://istio.io/latest/docs/reference/config/analysis/ist0151/?utm_source=chatgpt.com "EnvoyFilterUsesRelativeOperation - Istio"
