Ниже представлен подробный «шпаргалочный» путеводитель по всем каталогам-шаблонам, которые вы увидели в репозитории **The Good Docs Project**. Для каждого шаблона указаны назначение, целевая аудитория, рекомендуемая структура и ключевые приёмы. Каталоги сгруппированы по трём наборам, в каком порядке их обычно устанавливают в документационный стек проекта.

---

## Core Pack — базовые документы продукта

| Шаблон                 | Назначение                                                                          | Основные разделы                                                                                                                  |
| ---------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **concept**            | Объяснить идею/функцию до того, как пользователь перейдёт к практическим шагам.     | *Definition*, *Background*, (опц.) диаграмма, ссылки на how-to и reference. ([thegooddocsproject.dev][1])                         |
| **how-to**             | Пошагово решить 1 задачу опытного пользователя; до 10 шагов.                        | *Overview* → опц. *Before you begin* → *Steps* (плюс предупреждения «if this then that»). ([thegooddocsproject.dev][2])           |
| **tutorial**           | Дать новичку «первый успех» в безопасном сценарии (15-60 мин).                      | *Learning objectives* → *Before you begin* → *Steps* → *Next steps*. ([thegooddocsproject.dev][3])                                |
| **quickstart**         | Минимальный «Hello World» по ключевой фиче; < 1 час.                                | *Overview* → (опц.) *Install* → *Steps* / *Parts* → *Next steps*. ([thegooddocsproject.dev][4])                                   |
| **reference**          | Справочная таблица/список параметров, флагов, полей и т.д.                          | *Overview* + структурированный «тело» (таблицы, схемы); без процедур. ([thegooddocsproject.dev][5])                               |
| **installation-guide** | Установить и сконфигурировать продукт (stand-alone или встроенный README-раздел).   | *System requirements* → *Before you begin* → *Installation steps* → *Verify* → *Post-installation*. ([thegooddocsproject.dev][6]) |
| **troubleshooting**    | Симптом → причина → решение. Снижает нагрузку на саппорт.                           | *Introduction* → *Symptoms* → *Solutions* (нумерованные) → советы. ([thegooddocsproject.dev][7])                                  |
| **release-notes**      | Публичный отчёт о фичах/фикcах, отличие от changelog.                               | *New features*, *Improvements*, *Bug fixes*, *Known issues*; следовать SemVer. ([thegooddocsproject.dev][8])                      |
| **style-guide**        | Единые правила тона, терминов, форматирования; может ссылаться на Google Dev Style. | *Preferred style*, *Glossary of terms*, *Linters*, *Update process*. ([thegooddocsproject.dev][9])                                |

---

## API & Misc Pack — техническая деталь

| Шаблон                  | Назначение                                                                             | Ключевые особенности                                                                                                     |
| ----------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **api-getting-started** | «Самый короткий путь» к первому успешному REST-запросу; замена старого API quickstart. | *Prerequisites*, *Authentication*, *Base URL*, *First request*, *Next steps*. ([thegooddocsproject.dev][10])             |
| **api-reference**       | Полный мануал по эндпоинтам; рассчитан на автогенерацию + ручные вставки.              | 3 части: *Overview* → *Resource groups* → *Endpoint* блоки (метод, путь, схемы, примеры). ([thegooddocsproject.dev][11]) |
| **contact-support**     | Страница с каналами связи (чат, e-mail, KB).                                           | Сравнительная матрица «Contact support vs Contact us vs Support portal» + SLA. ([thegooddocsproject.dev][12])            |
| **glossary**            | Мини-словарь терминов; колонки Term/Abbrev/Definition/Source.                          | Рекомендует хранить только специфические термины; переводы — через Terminology System. ([thegooddocsproject.dev][13])    |
| **terminology-system**  | Расширенный многоязычный тезаурус (альтернативы, запрещённые варианты, локализация).   | Таблица Term / Definition / Usage (alt, rejected, related) / POS / Source / Updates. ([thegooddocsproject.dev][14])      |
| **style-guide**         | (см. Core Pack)                                                                        |                                                                                                                          |
| **readme**              | «Визитка» репозитория: зачем, как запустить, как помочь.                               | Блоки *Logo & Badges*, *Project Description*, *Install/Run*, *Contributing*, *License*. ([thegooddocsproject.dev][15])   |
| **reference**           | (см. Core Pack)                                                                        |                                                                                                                          |

---

## Community Pack — для OSS-экосистемы

| Шаблон                 | Назначение                                                         | Что внутри                                                                                                        |
| ---------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| **bug-report**         | Issue-template для GitHub/GitLab; повышает качество обращений.     | *Environment*, *Steps to reproduce*, *Observed vs Expected*, *Proof*, *Test data*. ([thegooddocsproject.dev][16]) |
| **changelog**          | Технический журнал всех изменений в обратной хронологии.           | Секции *Added*, *Changed*, *Deprecated*, *Fixed*, *Security*, *Breaking*. ([thegooddocsproject.dev][17])          |
| **contributing-guide** | Правила и workflow для внешних вкладов.                            | *Welcome*, *Ground rules*, *Types of contributions*, *Setup*, *PR process*. ([thegooddocsproject.dev][18])        |
| **our-team**           | Листинг ролей и контактов мейнтейнеров; поддерживает прозрачность. | Перечни команд, зон ответственности, способов связи. ([thegooddocsproject.dev][19])                               |
| **code-of-conduct**    | Политика поведения + комплект операционных документов.             | См. подтаблицу ниже. ([thegooddocsproject.dev][20])                                                               |

### Семейство Code of Conduct

| Каталог                              | Роль документа                                                                                                          |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| *code-of-conduct*                    | Основные правила, ожидаемое/недопустимое поведение, санкции. ([thegooddocsproject.dev][20])                             |
| *code-of-conduct-response-plan*      | Пошаговая процедура расследований, контакты модераторов, тренинги (Mozilla, Otter Tech). ([thegooddocsproject.dev][21]) |
| *code-of-conduct-incident-record*    | Форма для первоначального приёма жалобы; включает escrow-механику. ([thegooddocsproject.dev][22])                       |
| *code-of-conduct-remediation-record* | Протокол итоговой встречи с нарушителем; фиксирует план поведения и апелляцию. ([thegooddocsproject.dev][23])           |

---

## UX & Док-стратегия

| Шаблон            | Назначение                                                     | Особенности                                                                                         |
| ----------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **user-personas** | Моделирование ключевых типов пользователей (роль, цели, боли). | Связывает с user-stories и journey-maps; содержит пример DevOps Dan. ([thegooddocsproject.dev][24]) |

---

## Вспомогательные каталоги

| Каталог    | Что это                                                                            |
| ---------- | ---------------------------------------------------------------------------------- |
| **images** | Папка с PNG/SVG, используемыми в примерах и скриншотах шаблонов (логотипы, схемы). |

---

### Отдельное отличие «Release notes» vs «Changelog»

* **Release notes** — ориентированы на конечных пользователей, пишутся простым языком, группируются по фичам; номеруются по SemVer 2.0.0 или по дате. ([thegooddocsproject.dev][8], [thegooddocsproject.dev][8])
* **Changelog** — технический лог всех коммитов/PR; аудитория — разработчики; допускает детализированные ссылки на CVE. ([thegooddocsproject.dev][17])

---

## Как собирать свою документационную «партитуру»

1. **Старт**: README + Quickstart → дают первое впечатление.
2. **Обучение**: Concept → Tutorial.
3. **Работа**: How-to, Installation-guide, Troubleshooting.
4. **Справка**: Reference / API Reference (+ Glossary/Terminology).
5. **Комьюнити**: Contributing-guide, Code of Conduct bundle, Our Team.
6. **Релизы**: Changelog → Release notes (+ Bug-report шаблон на входе).

Следуя этой матрице и комбинируя шаблоны, легко быстро развернуть консистентный, «шумоустойчивый» набор документации под любой технический продукт.

[1]: https://www.thegooddocsproject.dev/template/concept "www.thegooddocsproject.dev"
[2]: https://www.thegooddocsproject.dev/template/how-to "www.thegooddocsproject.dev"
[3]: https://www.thegooddocsproject.dev/template/tutorial?utm_source=chatgpt.com "The tutorial template - The Good Docs Project"
[4]: https://www.thegooddocsproject.dev/template/quickstart "www.thegooddocsproject.dev"
[5]: https://www.thegooddocsproject.dev/template/reference "www.thegooddocsproject.dev"
[6]: https://www.thegooddocsproject.dev/template/installation-guide "www.thegooddocsproject.dev"
[7]: https://www.thegooddocsproject.dev/template/troubleshooting "www.thegooddocsproject.dev"
[8]: https://www.thegooddocsproject.dev/template/release-notes "www.thegooddocsproject.dev"
[9]: https://www.thegooddocsproject.dev/template/style-guide "www.thegooddocsproject.dev"
[10]: https://www.thegooddocsproject.dev/template/api-getting-started "www.thegooddocsproject.dev"
[11]: https://www.thegooddocsproject.dev/template/api-reference "www.thegooddocsproject.dev"
[12]: https://www.thegooddocsproject.dev/template/contact-support "www.thegooddocsproject.dev"
[13]: https://www.thegooddocsproject.dev/template/glossary "www.thegooddocsproject.dev"
[14]: https://www.thegooddocsproject.dev/template/terminology-system "www.thegooddocsproject.dev"
[15]: https://www.thegooddocsproject.dev/template/readme "www.thegooddocsproject.dev"
[16]: https://www.thegooddocsproject.dev/template/bug-report "www.thegooddocsproject.dev"
[17]: https://www.thegooddocsproject.dev/template/changelog "www.thegooddocsproject.dev"
[18]: https://www.thegooddocsproject.dev/template/contributing-guide "www.thegooddocsproject.dev"
[19]: https://www.thegooddocsproject.dev/template/our-team "www.thegooddocsproject.dev"
[20]: https://www.thegooddocsproject.dev/template/code-of-conduct "www.thegooddocsproject.dev"
[21]: https://www.thegooddocsproject.dev/template/code-of-conduct-response-plan "www.thegooddocsproject.dev"
[22]: https://www.thegooddocsproject.dev/template/code-of-conduct-incident-record "www.thegooddocsproject.dev"
[23]: https://www.thegooddocsproject.dev/template/code-of-conduct-remediation-record "www.thegooddocsproject.dev"
[24]: https://www.thegooddocsproject.dev/template/user-personas "www.thegooddocsproject.dev"




---
---
---

За основу «универсального» каркаса можно взять пересечение требований стандартов ISO 82079-1 (информация для использования), ISO / IEC / IEEE 26515 (док-процесс), правил контроля документации ISO 9001 и практик Diátaxis / The Good Docs Project. Эти источники сходятся в том, что любой тех-документ — от архитектурного решения до how-to — должен давать читателю *ответы на одни и те же базовые вопросы*: что это, для кого, при каких условиях применять, как убедиться в результате и как отследить изменения. ([instrktiv.com][1], [cdn.standards.iteh.ai][2], [diataxis.fr][3], [thegooddocsproject.dev][4], [blog.invgate.com][5], [qualitysystems.com][6])

## Набор обязательных разделов

> Ниже перечислены секции, которые стоит делать **обязательными** для любого технического документа. Формулировки можно адаптировать к формату (MD-файл, Confluence-страница, PDF), но сами данные должны присутствовать всегда.

| #  | Раздел                                                           | Цель / ключевые вопросы                                                                                                |
| -- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1  | **Title & Metadata** (ID, версия, дата, статус, автор, владельц) | Однозначно идентифицирует документ и его актуальность. Требуется ISO 9001 для «идентификации и описания».              |
| 2  | **Purpose / Overview**                                           | Что за проблему решает документ? Какую пользу несёт читателю?                                                          |
| 3  | **Audience & Scope**                                             | Для кого написано, какой уровень знаний предполагается и какие границы охватывает материал.                            |
| 4  | **Context / Background**                                         | Краткая предыстория, архитектурные предпосылки или бизнес-требования, необходимые для понимания основной части.        |
| 5  | **Prerequisites / Before you start**                             | Технические и организационные условия, права доступа, версии ПО, ограничения.                                          |
| 6  | **Main Content**                                                 | Собственно дизайн, процедура или инструкция — структура зависит от типа документа (диаграммы, numbered steps и т. д.). |
| 7  | **Expected Results / Acceptance**                                | Как выглядит успешный исход: критерии приёмки, коды ответа, метрики.                                                   |
| 8  | **Validation / Test**                                            | Шаги или ссылки на тест-кейсы, которыми можно подтвердить работоспособность решения.                                   |
| 9  | **Next Steps / Post-conditions**                                 | Что делать после выполнения процедуры: очистка среды, развёртывание в прод, плановое обслуживание.                     |
| 10 | **Related Docs & References**                                    | Ссылки на API-справку, концепты, RFC, дефект-лист. Держит читателя в едином инфопространстве.                          |
| 11 | **Glossary / Acronyms**                                          | Определения терминов, чтобы исключить неоднозначность (особенно полезно для разноязычных команд).                      |
| 12 | **Change Log / Revision History**                                | Сводка всех изменений с номерами версий и кратким описанием.                                                           |
| 13 | **Review & Approval Record**                                     | Кто, когда и с каким результатом проверил документ (peer, SME, compliance), плюс дата следующего планового ревью.      |
| 14 | **Ownership & Contact**                                          | Как связаться с автором или ответственным за сопровождение.                                                            |
| 15 | **License / Compliance**                                         | Условия использования кода, схем, данных; соответствие нормативам или внутренним политикам.                            |

Эти пятнадцать пунктов покрывают весь жизненный цикл информации: создание → применение → проверка → поддержка. ([atlassian.com][7], [graphapp.ai][8], [dmeg.cessda.eu][9])

### Почему именно они?

* **Metadata + Change Log** позволяют аудиторам и коллегам мгновенно понять, «правильную» ли версию они читают. ISO 9001 прямо требует контроля ревизий. ([qualitysystems.com][6])
* **Audience, Scope, Context** снимают главный риск неправильного использования: стандарт 82079 подчёркивает, что информация должна быть «для целевой аудитории». ([instrktiv.com][1])
* **Prerequisites** экономят время: ISO 26515 советует фиксировать все «assumptions and dependencies», чтобы команда Agile не спотыкалась на полпути. ([cdn.standards.iteh.ai][2])
* **Expected Results + Validation** — способ «закрыть» Definition of Done и убрать споры о качестве. Atlassian в шаблоне SDD отдельно выделяет «assumptions, dependencies, acceptance». ([atlassian.com][7])
* **Related Docs, Glossary** поддерживают связность контента (Diátaxis: «документы должны находиться друг через друга»). ([diataxis.fr][3])
* **Review Record** отделяет «утверждение» от «рецензирования» и пригодится при внешних проверках (GDPR, SOX). Практику подтверждают The Good Docs и InvGate. ([thegooddocsproject.dev][4], [blog.invgate.com][5])

### Как внедрить

1. **Создайте шаблон-фронтматтер** (YAML/JSON) с полями из пунктов 1, 12-15; он будет автоматически заполняться через CI.
2. **Добавьте секции 2-11 в тело** — порядок можно менять, но заголовки держите стабильными, чтобы поисковый движок Confluence или Docs-Site корректно строил ToC.
3. **CI-проверка**: линтер проверяет наличие всех обязательных секций перед merge.
4. **Нотация**: используйте одинаковые якоря (`## Purpose`, `## Prerequisites`) — это облегчает генерацию навигации и экспорт в PDF.

### Пример минимального каркаса (Markdown)

```markdown
---
title: "Title of the Document"
doc-id: SYS-ARCH-042
version: "1.2.0"
status: Approved
author: L. Ivanov
owner: platform-team@example.com
created: 2025-07-02
updated: 2025-07-15
next-review: 2026-07-15
license: CC-BY-SA-4.0
---

## Purpose / Overview
...

## Audience & Scope
...

## Context / Background
...

## Prerequisites
...

## Main Content
...

## Expected Results
...

## Validation / Test
...

## Next Steps
...

## Related Docs & References
...

## Glossary
...

## Change Log
| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.2.0 | 2025-07-15 | L. Ivanov | Added validation section |

## Review & Approval Record
| Version | Reviewer | Date | Outcome |
|---------|----------|------|---------|
| 1.2.0 | Q. Chen | 2025-07-16 | Approved |
```

Следуя этому перечню, вы получите единообразную рамку, пригодную и для архитектурных томов, и для кратких инструкций, и для пользовательских руководств — без потери специфики каждого жанра.

[1]: https://instrktiv.com/en/82079/ "Definitive Guide to EN 82079 on Creating Information For Use"
[2]: https://cdn.standards.iteh.ai/samples/70880/1d67e3a097bf410a9a4ce292aa8b0c8b/ISO-IEC-IEEE-26515-2018.pdf "ISO/IEC/IEEE 26515:2018 - ISO/IEC/IEEE 26515:2018"
[3]: https://diataxis.fr/ "Diátaxis"
[4]: https://www.thegooddocsproject.dev/template "The Good Docs Project Template Guides"
[5]: https://blog.invgate.com/technical-documentation "Technical Documentation: Best Practices, Formats, And Examples"
[6]: https://www.qualitysystems.com/blog/revision-number-revision-date-or-both/ "Quality Systems - Revision Number, Revision Date or Both?"
[7]: https://www.atlassian.com/work-management/knowledge-sharing/documentation/software-design-document " Software Design Document [Tips & Best Practices] | The Workstream "
[8]: https://www.graphapp.ai/blog/the-ultimate-technical-documentation-template-a-comprehensive-guide "The Ultimate Technical Documentation Template: A Comprehensive Guide | Graph AI"
[9]: https://dmeg.cessda.eu/Data-Management-Expert-Guide/2.-Organise-Document/Documentation-and-metadata "Documentation and metadata - Data Management Expert Guide"
