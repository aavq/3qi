**TL;DR — у вас исчезла «GitHub-шная» таблица, потому что вместо неё в команду попал только CSS Highlight.js.
Верните таблице собственный стиль (ещё один `--css`), либо подключите более «богатую» тему (Tailwind Typography, Bootstrap и т.п.) или пропишите пару правил вручную. Ниже — готовые рецепты с пояснениями.**

---

## 1  Почему таблица «голая»

| Что случилось                                                                                                                                                                                                     | Источник |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `github-markdown.css` вообще не подключён, поэтому селекторы, делающие табличку серо-белой с тонкими границами, не применяются. Highlight.js CSS красит **только** код. ([github.com][1], [stackoverflow.com][2]) |          |
| Pandoc допускает **несколько** ключей `--css`; они подхватываются по порядку. Если передать лишь один файл, остальные темы пропадут. ([pandoc.org][3])                                                            |          |

---

## 2  Минимальное решение: вернуть GitHub-CSS

```bash
pandoc EnvoyOAuth2Filters.md -s \
  --embed-resources \
  -o out.html \
  --highlight-style=tango \
  --metadata title="Istio – OAuth2 filter how-to" \
  --css https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.0/github-markdown-light.min.css \
  --css https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css \
  --include-before-body <(echo '<article class="markdown-body">') \
  --include-after-body  <(echo '</article>')
```

*Что поменялось — добавили второй `--css`, в итоге:*

* таблицы получают ту же сетку/отступы, что и на GitHub; ([github.com][1])
* подсветка кода остаётся «dark» от Highlight.js. ([github.com][4])

---

## 3  Tailwind Typography — «красиво из коробки»

Если хотите шире поля, читаемый шрифт и обтекание картинок, проще всего взять Tailwind Typography:

```bash
# 1 — тащим CDN-версию Tailwind + plugin
echo '<script src="https://cdn.tailwindcss.com?plugins=typography"></script>' > head.html

# 2 — пересобираем
pandoc EnvoyOAuth2Filters.md -s \
  --embed-resources \
  --include-in-header=head.html \
  --highlight-style=tango \
  --metadata title="Istio – OAuth2 filter how-to" \
  --include-before-body <(echo '<article class="prose lg:prose-xl mx-auto">') \
  --include-after-body  <(echo '</article>') \
  -o out_tailwind.html
```

Tailwind `prose` даёт:

* выравнивание и отступы у `<table>`;
* авто-типографику для `ul /li`, `blockquote`, т.д. ([tailwindcss.com][5], [v1.tailwindcss.com][6])

---

## 4  Bootstrap + полосатые таблицы

Любите классические рамки? Подключаем Bootstrap и добавляем класс `table` каждому `<table>` через Lua-фильтр:

**`tableclass.lua`**

```lua
function Table (tbl)
  tbl.attr.classes:insert('table')
  tbl.attr.classes:insert('table-striped')
  tbl.attr.classes:insert('table-bordered')
  return tbl
end
```

**Команда**

```bash
pandoc EnvoyOAuth2Filters.md -s \
  --lua-filter=tableclass.lua \
  --css https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css \
  --highlight-style=tango \
  --embed-resources \
  -o out_bootstrap.html
```

Класс `.table` активирует встроенные правила Bootstrap для ширины, границ и зебры. ([getbootstrap.com][7])

---

## 5  Свой 5-строчный CSS

Нужен только тонкий серый бордер? Создайте `mytables.css`:

```css
table {
  border-collapse: collapse;
  margin: 1.2em 0;
  width: 100%;
}
table th, table td {
  border: 1px solid #d0d7de;
  padding: .4em .8em;
}
table th { background: #f6f8fa; font-weight: 600; }
```

И добавьте ещё один `--css mytables.css`.
Подход гибкий и не тянет фреймворки. ([stackoverflow.com][8])

---

## 6  Проверочный чек-лист

1. **Несколько `--css`** — Pandoc их поддерживает; порядок важен. ([pandoc.org][3])
2. **Обёртка** — для GitHubCSS нужна `.markdown-body`; для Tailwind — `.prose`. ([github.com][1], [tailwindcss.com][5])
3. **`--embed-resources`** скачает и встроит даже CDN-файл, так что итоговый HTML самодостаточен. ([getbootstrap.com][9])
4. **Подсветка** — не конфликтует с таблицами, но лучше держать свой Highlight.css файл отдельно. ([github.com][4])
5. **При необходимости классов** (Bootstrap или свои) — добавляйте их сразу в Markdown (`|---| {.table}`) или Lua-фильтром. ([stackoverflow.com][10], [pandoc.org][11])

---

### Итог

*Самый быстрый путь* — вернуть GitHub Markdown CSS вторым `--css`.
*Чуть круче* — Tailwind Typography: всё красиво и адаптивно.
*Нужны бордеры и «зебра»* — Bootstrap + Lua-фильтр или пара строк собственного CSS.

[1]: https://github.com/sindresorhus/github-markdown-css?utm_source=chatgpt.com "The minimal amount of CSS to replicate the GitHub Markdown style"
[2]: https://stackoverflow.com/questions/42664314/make-master-table-of-contents-covering-several-separate-input-files-using-pandoc?utm_source=chatgpt.com "Make master table of contents covering several separate input files ..."
[3]: https://pandoc.org/demo/example33/3.4-options-affecting-specific-writers.html?utm_source=chatgpt.com "3.4 Options affecting specific writers - Pandoc"
[4]: https://github.com/jgm/pandoc/issues/6496?utm_source=chatgpt.com "How to set a custom-style for a table? #6496 - jgm/pandoc - GitHub"
[5]: https://tailwindcss.com/docs/typography-plugin?utm_source=chatgpt.com "tailwindlabs/tailwindcss-typography: Beautiful typographic defaults ..."
[6]: https://v1.tailwindcss.com/docs/typography-plugin?utm_source=chatgpt.com "@tailwindcss/typography - Tailwind CSS"
[7]: https://getbootstrap.com/docs/4.1/content/tables/?utm_source=chatgpt.com "Tables - Bootstrap"
[8]: https://stackoverflow.com/questions/27300329/table-with-borders-in-html-and-latex-output-from-markdown-source-with-pandoc?utm_source=chatgpt.com "Table with borders in HTML and LaTeX output from Markdown ..."
[9]: https://getbootstrap.com/docs/4.1/layout/grid/?utm_source=chatgpt.com "Grid system - Bootstrap"
[10]: https://stackoverflow.com/questions/41877612/pandoc-add-class-to-table-in-markdown?utm_source=chatgpt.com "pandoc add class to table in markdown - Stack Overflow"
[11]: https://pandoc.org/lua-filters.html?utm_source=chatgpt.com "Pandoc Lua Filters"
