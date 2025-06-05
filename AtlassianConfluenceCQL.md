**Кратко**
Поиск можно классифицировать как минимум по трём осям — по цели запроса (что пользователь хочет), по технологии индексации и ранжирования (как система «понимает» и ищет), а также по интерфейсу взаимодействия (как пользователь формулирует запрос).
Atlassian Confluence использует классический полнотекстовый поиск на базе Apache Lucene (инвертированный индекс, булева алгебра, стемминг и т. д.) и поверх него предоставляет язык CQL для «расширенного» поиска; в версиях Data Center доступен слой Atlassian Search Platform, позволяющий переключить движок с Lucene на OpenSearch/Elasticsearch или выносить индекс наружу. ([support.atlassian.com][1], [developer.atlassian.com][2], [jira.atlassian.com][3], [confluence.atlassian.com][4])

---

## 1. Классификация по цели запроса (User Intent)

| Тип                | Что ищет пользователь         | Пример                       |
| ------------------ | ----------------------------- | ---------------------------- |
| **Информационный** | получить знания/ответ         | «kubernetes liveness probe»  |
| **Навигационный**  | перейти к конкретному ресурсу | «atlassian confluence login» |
| **Транзакционный** | совершить действие/покупку    | «buy milvus cloud»           |

([textbroker.com][5], [wordstream.com][6])

---

## 2. Классификация по технологии и алгоритму

### 2.1 Ключевые «модели» поиска

| Модель               | Кратко                                              | Типичный стек                                                                                         |
| -------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Булев / ключевой** | точные операторы AND/OR/NOT, маски, proximity       | Lucene, Solr ([support.atlassian.com][1])                                                             |
| **Полнотекстовый**   | инвертированный индекс, стемминг, стоп-слова        | Lucene, Postgres GIN                                                                                  |
| **Фасетный**         | фильтры-грани (facets) для узкой навигации          | e-commerce движки, Algolia ([dynamicyield.com][7], [algolia.com][8], [addsearch.com][9])              |
| **Нечёткий / Fuzzy** | автом. исправление опечаток, расстояние Левенштейна | Lucene \~                                                                                             |
| **Семантический**    | векторные представления, поиск «по смыслу»          | Milvus, Weaviate ([learn.microsoft.com][10], [zilliz.com][11], [instaclustr.com][12], [lumar.io][13]) |
| **Гибридный**        | объединяет векторный и полнотекстовый ранкинг       | Azure AI Search, OpenSearch k-NN ([learn.microsoft.com][10])                                          |

### 2.2 По архитектуре хранения индекса

* **Embedded-Lucene** (встроенный в JVM, локальные файлы) — как в Confluence Server ([support.atlassian.com][1])
* **Remote Elasticsearch/OpenSearch cluster** — горизонтальное масштабирование; опция в Confluence Data Center 8+ ([jira.atlassian.com][3])
* **Vector store** (HNSW, IVF-PQ и др.) — Pinecone, pgvector ([datacamp.com][14], [cloudraft.io][15])

---

## 3. Классификация по интерфейсу

| Интерфейс                  | Описание                           | Пример реализации                                         |
| -------------------------- | ---------------------------------- | --------------------------------------------------------- |
| **Простое текстовое поле** | одна строка, «Google-style»        | Confluence «Search bar»                                   |
| **Расширенный синтаксис**  | поля, операторы, кавычки, маски    | Lucene Query Syntax                                       |
| **Фильтры/фасеты**         | чекбоксы, слайдеры, теги           | AddSearch, Algolia ([addsearch.com][9], [algolia.com][8]) |
| **DSL/API-язык**           | REST-DSL, SQL-подобный язык        | Confluence CQL ([developer.atlassian.com][2])             |
| **NLP-запрос (NLQ)**       | «покажи страницы за прошлый месяц» | Chat-search на векторном индексе                          |

---

## 4. Как устроен поиск в Atlassian Confluence

### 4.1 Движок и индексация

* **Lucene** — основной полнотекстовый движок; индекс хранится в `<confluence-home>/index` ([support.atlassian.com][1])
* **Событийная индексация** — при создании/обновлении контента Confluence генерирует события, которые пополняют индекс.
* **Data Center**: с версии 8 Atlassian Search Platform даёт возможность выносить индекс в **OpenSearch/Elasticsearch**, сохраняя API CQL неизменным ([jira.atlassian.com][3], [confluence.atlassian.com][4])

### 4.2 Язык запросов CQL

* SQL-подобная конструкция: `space = "DEV" AND type = page` ([developer.atlassian.com][2])
* Поддержка `CONTAINS`, `!~`, `IN`, диапазонов дат и сортировки `ORDER BY`.
* В UI эти возможности скрыты за кнопкой **Advanced Search** или применяются в макросах «Content by label» и др. ([confluence.atlassian.com][16])

### 4.3 Расширения и плагины

* Плагин-коннектор позволяет выполнять запросы напрямую к внешнему Elasticsearch кластеру (для аналитики логов и др.) ([marketplace.atlassian.com][17])

### 4.4 Что получите «из коробки»

| Возможность                                | Наличие                 |
| ------------------------------------------ | ----------------------- |
| Стемминг/синонимы для основных языков      | ✓ Lucene Analyzers      |
| Булевы операторы, wildcards `*`, fuzzy `~` | ✓                       |
| Поиск по вложениям (PDF, DOCX и т. д.)     | ✓ Tika-based extraction |
| Подсветка фрагментов (snippets)            | ✓                       |
| Фасеты (по пространствам, авторам, типам)  | ✓ в панели фильтров UI  |

---

## 5. Примеры CQL-запросов для ежедневной работы

```text
# 1. Все страницы в пространстве DEV, изменённые за последние 14 дней
space = "DEV" AND type = page AND lastModified > now("-14d")

# 2. Блог-посты, где title содержит "roadmap", кроме лично ваших
type = blogpost AND title ~ "roadmap" AND NOT creator = currentUser()

# 3. Документы в пространствах OPS или PLATFORM с меткой "runbook"
(space IN (OPS, PLATFORM)) AND label = runbook
```

([developer.atlassian.com][2])

---

## 6. Что это значит для DevOps-платформы

* **Тонкая настройка**: можно подключать собственные Lucene Analyzer-плагины (например, для k-stem русского) или внешний Elasticsearch, если нужен векторный поиск.
* **Масштабирование**: при росте объёма знаний (> миллионов документов) имеет смысл вынести индекс в OpenSearch-кластер и включить репликацию/Data Center.
* **Семантический апгрейд**: если нужно «понять» запросы инженеров свободным языком, добавляйте векторный слой поверх существующей CQL-фильтрации — гибрид показывает лучшие результаты. ([learn.microsoft.com][10], [lumar.io][13])

---

### Дополнительные материалы

1. Boolean vs Semantic Search — Aaron Tay ([aarontay.medium.com][18])
2. Faceted Search Best Practices — Dynamic Yield ([dynamicyield.com][7])
3. Open-Source Vector Engines 2025 — Zilliz Blog ([zilliz.com][11])
   *(и др. — см. ссылки выше)*

---

**Вопрос к вам**
Нужно ли глубже разобрать настройку Lucene-анализаторов, создание собственных CQL-полей или подключение внешнего Elasticsearch-кластера? Я могу подготовить пошаговые инструкции или примеры конфигурации.

[1]: https://support.atlassian.com/confluence/kb/how-to-view-the-contents-of-the-search-index-in-confluence-server-and-data-center/ "How to view the contents of the search index in Confluence Server and Data Center | Confluence | Atlassian Support"
[2]: https://developer.atlassian.com/server/confluence/advanced-searching-using-cql/ "Advanced Searching using CQL"
[3]: https://jira.atlassian.com/browse/CONFSERVER-96112?utm_source=chatgpt.com "Support for Elasticsearch | Confluence Data Center - Jira"
[4]: https://confluence.atlassian.com/adminjiraserver/migrating-from-lucene-to-search-api-1574503524.html?utm_source=chatgpt.com "Migrating from Lucene to Search API - Atlassian Documentation"
[5]: https://www.textbroker.com/types-searches-transactional-navigational-informational?utm_source=chatgpt.com "Types of searches: transactional, navigational, informational"
[6]: https://www.wordstream.com/blog/ws/2012/12/10/three-types-of-search-queries?utm_source=chatgpt.com "The 3 Types of Search Queries & How You Should Target Them"
[7]: https://www.dynamicyield.com/glossary/faceted-search/?utm_source=chatgpt.com "Faceted Search Definition, Examples & Best Practices - Dynamic Yield"
[8]: https://www.algolia.com/blog/ux/faceted-search-an-overview?utm_source=chatgpt.com "Faceted Search: An Overview - Algolia"
[9]: https://www.addsearch.com/blog/faceted-search/?utm_source=chatgpt.com "What is Faceted Search? Examples and Explanation - AddSearch"
[10]: https://learn.microsoft.com/en-us/azure/search/search-what-is-an-index "Search index overview - Azure AI Search | Microsoft Learn"
[11]: https://zilliz.com/blog/top-5-open-source-vector-search-engines?utm_source=chatgpt.com "Top 5 Open Source Vector Search Engines in 2025 - Zilliz blog"
[12]: https://www.instaclustr.com/education/vector-database/vector-search-vs-semantic-search-4-key-differences-and-how-to-choose/?utm_source=chatgpt.com "Vector search vs semantic search: 4 key differences and how to ..."
[13]: https://www.lumar.io/blog/best-practice/semantic-search-explained-vector-models-impact-on-seo/?utm_source=chatgpt.com "Semantic Search Explained: Vector Models' Impact on SEO Today"
[14]: https://www.datacamp.com/blog/the-top-5-vector-databases?utm_source=chatgpt.com "The 7 Best Vector Databases in 2025 - DataCamp"
[15]: https://www.cloudraft.io/blog/top-5-vector-databases?utm_source=chatgpt.com "Top 5 Vector Databases in 2025 - CloudRaft"
[16]: https://confluence.atlassian.com/display/DOC/Confluence%2BSearch%2BFields?utm_source=chatgpt.com "Confluence Search Fields - Atlassian Documentation"
[17]: https://marketplace.atlassian.com/apps/1234440/connector-for-elasticsearch-and-confluence?utm_source=chatgpt.com "Connector for Elasticsearch and Confluence - Atlassian Marketplace"
[18]: https://aarontay.medium.com/boolean-vs-keyword-lexical-search-vs-semantic-keeping-things-straight-95eb503b48f5?utm_source=chatgpt.com "Boolean vs Keyword/Lexical search vs Semantic — keeping things ..."
