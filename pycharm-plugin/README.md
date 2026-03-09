# SyntaxSurge Bridge — плагин для PyCharm

Плагин отправляет позицию курсора и контекст строк на мост SyntaxSurge (`http://127.0.0.1:8765/cursor`) с `source: "pycharm"`, чтобы автопечать кода могла синхронизироваться с редактором.

---

## Что нужно

- **PyCharm** (Community или Professional) — желательно 2023.2 или новее.
- **JDK 17** — для сборки плагина (обычно уже есть с PyCharm/IDEA).

---

## 1. Под свою версию PyCharm (по желанию)

По умолчанию плагин собирается под **IntelliJ 2024.1** и совместим с PyCharm 2024.x. Если у тебя другая версия PyCharm, открой в проекте файл **`build.gradle.kts`** и поправь блок `intellij` и `patchPluginXml`:

```kotlin
intellij {
    version.set("2024.1")   // версия платформы: 2023.2, 2024.1, 2024.2 и т.д.
    type.set("IC")           // IC = IntelliJ Community (подходит для PyCharm)
    plugins.set(listOf())
}

// ...

patchPluginXml {
    sinceBuild.set("241")   // минимум: 232 = 2023.2, 241 = 2024.1, 242 = 2024.2
    untilBuild.set("241.*") // максимум: оставь "241.*" или "242.*" под свою версию
}
```

Соответствие версий: **232** = 2023.2, **241** = 2024.1, **242** = 2024.2. Узнать build своей IDE: **Help → About** — в скобках будет число вроде `241.15990.20`.

---

## 2. Сборка плагина

### Вариант А: из PyCharm / IntelliJ IDEA (проще всего)

1. Открой папку **`pycharm-plugin`** как проект (File → Open).
2. Дождись окончания импорта Gradle (внизу прогресс).
3. Справа открой **Gradle**, разверни **syntaxsurge-bridge-pycharm → Tasks → intellij**.
4. Дважды щёлкни **buildPlugin**.

Готовый архив появится в **`build/distributions/syntaxsurge-bridge-pycharm-0.1.0.zip`**.

### Вариант Б: из командной строки

В каталоге **`pycharm-plugin`**:

**Если есть Gradle Wrapper** (файлы `gradlew` / `gradlew.bat` и `gradle/wrapper/gradle-wrapper.jar`):

- Windows: `gradlew.bat build`
- Linux/macOS: `./gradlew build`

**Если Wrapper нет** — открой проект в PyCharm/IDEA (см. вариант А) и собери через **buildPlugin**; IDE может создать wrapper. Либо установи [Gradle](https://gradle.org/install/) и в `pycharm-plugin` выполни: `gradle wrapper`, затем снова `gradlew.bat build` или `./gradlew build`.

Артефакт: **`build/distributions/syntaxsurge-bridge-pycharm-0.1.0.zip`**.

---

## 3. Установка в PyCharm

1. В PyCharm: **File → Settings** (или **Ctrl+Alt+S**).
2. Слева выбери **Plugins**.
3. Справа вверху нажми **⚙️** → **Install Plugin from Disk...**.
4. Укажи файл **`syntaxsurge-bridge-pycharm-0.1.0.zip`** из `pycharm-plugin/build/distributions/`.
5. Нажми **OK**, затем **Apply**. По запросу перезапусти IDE.

---

## 4. Проверка

1. Запусти мост SyntaxSurge: `python gui_typer.py` или `python run.py <файл>`.
2. В PyCharm открой любой файл в редакторе.
3. **Help → Find Action** (**Ctrl+Shift+A**), введи: **SyntaxSurge: проверить подключение к мосту** и выполни.
4. Должно появиться уведомление вроде: «Мост принял данные. Строка N, столбец M.»

---

## Кратко

| Шаг | Действие |
|-----|----------|
| 1 | (по желанию) В `build.gradle.kts` поправить `version.set("...")` и `sinceBuild` / `untilBuild` под свою версию PyCharm. |
| 2 | Собрать: открыть `pycharm-plugin` в IDE → Gradle → intellij → **buildPlugin** (или из консоли: `gradlew.bat build`). |
| 3 | Установить: **Settings → Plugins → ⚙️ → Install Plugin from Disk...** → выбрать `build/distributions/syntaxsurge-bridge-pycharm-0.1.0.zip`. |
| 4 | Перезапустить PyCharm. |

После установки плагин при смене вкладки и движении курсора отправляет на мост данные в формате, совместимом с `typer/cursor_bridge.py` (`source: "pycharm"`).
