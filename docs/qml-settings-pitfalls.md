# QML 设置页实现注意（踩过的坑）

来源：2026-09-29 设置页优化。症状与原因都经过实测复现，改动设置页相关 QML 前先看这一页。

## 1. `childrenRect` 不能给布局子项撑高

- 症状：卡片内容区高度为 0，页面 `contentHeight` 只剩标题高度，卡片被压扁。
- 原因：内容区的子项是 `GridLayout`/`ColumnLayout` 时，父 Item 的 `childrenRect.height` 不会随布局的隐式高度更新。
- 做法：让内容直接进卡片的 `ColumnLayout`（见 qml/SettingsCard.qml），卡片高度用 `layout.implicitHeight`；不要用「Item + childrenRect + 中转属性」的写法。

## 2. `font.pixelSize` 只能是整数

- 症状：组件加载失败，报 `Invalid property assignment: int expected`，且报错行号指向下一行。
- 原因：`font.pixelSize` 是 int，写 `11.5` 会被当成实数而失败。
- 做法：说明文字统一用 11，正文 12。

## 3. Layout 子项不能使用 anchors

- 症状：`Detected anchors on an item that is managed by a layout` 警告，行为未定义。
- 做法：放进 RowLayout/ColumnLayout/GridLayout 的组件用 `Layout.fillWidth`/`Layout.preferredHeight`；需要铺满父项的守卫组件改用显式 `width: parent.width` / `height: parent.height`（见 qml/SettingsWheelGuard.qml）。

## 4. ComboBox 会吞掉滚轮，导致整页滚不动

- 症状：鼠标停在任意下拉框上时页面无法滚动，停在空白处正常。
- 原因：Qt 6 的 `QQuickComboBox::wheelEvent` 在特定条件下无条件 `accept()`；`wheelEnabled: false` 会让情况更糟（连事件都不再冒泡）。
- 做法：给页面里**每一个** ComboBox 挂 `SettingsWheelGuard`（放在 ComboBox 内部），守卫直接驱动外层 Flickable 的 `contentY`；选项弹层是独立窗口，展开后仍可滚动选项。

## 5. 可滚动页面的高度

- 结构：`Flickable { contentWidth: width - scrollBar.width; contentHeight: contentEnd.y }`，内容列末尾放一个 `implicitHeight: 0` 的 `Item` 作为高度锚点；这样布局更新后一定会重新求值。
- 不要依赖 `content.implicitHeight`：布局更新后该绑定可能不再重新求值（实测停在旧值）。
