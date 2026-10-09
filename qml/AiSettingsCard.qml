import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

SettingsCard {
    id: card
    objectName: "aiSettingsCard"
    property var ai: backend.aiCampaign
    title: "AI 催交话术"
    description: "保存后在催办工作台「生成群发名单」中使用。生成会将名单内姓名、学号和当前欠课／欠作业发送给所选服务。API Key 由 Windows 凭据管理器保管。"
    function load() {
        var c = ai.config
        provider.currentIndex = c.provider === "doubao" ? 0 : 1
        address.text = c.base_url; modelName.text = c.model
        temperature.text = String(c.temperature); tokens.text = String(c.max_tokens)
        timeout.text = String(c.timeout); retries.text = String(c.retries)
        mode.currentIndex = ["person", "batch", "all"].indexOf(c.mode)
        batchSize.text = String(c.batch_size); concurrency.text = String(c.concurrency)
        apiKey.text = ""
    }
    function save() {
        var ok = ai.saveConfig({provider:provider.currentIndex === 0 ? "doubao" : "compatible",
            base_url:address.text, model:modelName.text, temperature:Number(temperature.text),
            max_tokens:Number(tokens.text), timeout:Number(timeout.text), retries:Number(retries.text),
            mode:["person", "batch", "all"][mode.currentIndex], batch_size:Number(batchSize.text),
            concurrency:Number(concurrency.text)}, apiKey.text)
        if (ok) apiKey.text = ""
        return ok
    }
    Component.onCompleted: load()
    GridLayout {
        Layout.fillWidth: true; columns: 2; columnSpacing: 12; rowSpacing: 8
        enabled: !card.ai.busy
        Label { text: "服务商"; color: UiTheme.muted }
        UiComboBox {
            id: provider; objectName: "aiProvider"; Layout.fillWidth: true
            model: ["豆包 API", "OpenAI 兼容"]
            Accessible.name: "AI 服务商"
            onActivated: address.text = currentIndex === 0 ? "https://ark.cn-beijing.volces.com/api/v3" : "https://api.openai.com/v1"
            SettingsWheelGuard { view: card.pageScroll }
        }
        Label { text: "服务地址"; color: UiTheme.muted }
        UiTextField { id: address; objectName: "aiBaseUrl"; Layout.fillWidth: true; Accessible.name: "AI 服务地址"; placeholderText: "HTTPS 地址，包含 /v1 或 /api/v3" }
        Label { text: "API Key"; color: UiTheme.muted }
        UiTextField { id: apiKey; objectName: "aiApiKey"; Layout.fillWidth: true; echoMode: TextInput.Password; Accessible.name: "AI API Key"; placeholderText: "留空沿用该服务已保存的密钥" }
        Label { text: "模型／接入点"; color: UiTheme.muted }
        UiTextField { id: modelName; objectName: "aiModel"; Layout.fillWidth: true; Accessible.name: "AI 模型名称或接入点 ID"; placeholderText: "填写服务商支持的模型名称或 ep-…" }
        Label { text: "默认生成方式"; color: UiTheme.muted }
        UiComboBox {
            id: mode; objectName: "aiDefaultMode"; Layout.fillWidth: true
            model: ["逐人", "分批（推荐）", "一次生成全部"]
            Accessible.name: "默认 AI 生成方式"
            SettingsWheelGuard { view: card.pageScroll }
        }
    }
    UiButton {
        id: advanced; text: checked ? "收起生成参数" : "展开生成参数"; checkable: true
        objectName: "aiAdvancedSettings"
    }
    GridLayout {
            Layout.fillWidth: true; visible: advanced.checked
            columns: card.width < 650 ? 2 : 4; columnSpacing: 8; rowSpacing: 8; enabled: !card.ai.busy
            Label { text: "温度"; color: UiTheme.muted }
            UiTextField { id: temperature; objectName: "aiTemperature"; Layout.fillWidth: true; Accessible.name: "AI 温度" }
            Label { text: "输出 tokens"; color: UiTheme.muted }
            UiTextField { id: tokens; objectName: "aiMaxTokens"; Layout.fillWidth: true; Accessible.name: "最大输出 tokens" }
            Label { text: "超时（秒）"; color: UiTheme.muted }
            UiTextField { id: timeout; objectName: "aiTimeout"; Layout.fillWidth: true; Accessible.name: "AI 请求超时秒数" }
            Label { text: "自动重试次数"; color: UiTheme.muted }
            UiTextField { id: retries; objectName: "aiRetries"; Layout.fillWidth: true; Accessible.name: "AI 自动重试次数" }
            Label { text: "每批人数"; color: UiTheme.muted }
            UiTextField { id: batchSize; objectName: "aiBatchSize"; Layout.fillWidth: true; Accessible.name: "AI 每批人数" }
            Label { text: "并发批数"; color: UiTheme.muted }
            UiTextField { id: concurrency; objectName: "aiConcurrency"; Layout.fillWidth: true; Accessible.name: "AI 并发批数" }
    }
    Label { text: "一次生成受模型输出上限限制；人数较多时建议分批。模型须支持 Chat Completions、JSON 输出及上述参数。"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted; font.pixelSize: 12 }
    Label { text: card.ai.notice; objectName: "aiSettingsNotice"; Layout.fillWidth: true; wrapMode: Text.Wrap; color: UiTheme.muted }
    footer: RowLayout {
        Layout.fillWidth: true
        UiButton { objectName: "saveAiConfig"; text: "保存配置"; enabled: !card.ai.busy; onClicked: card.save() }
        UiButton { objectName: "testAiConnection"; text: card.ai.busy ? "请求中…" : "保存并测试连接"; enabled: !card.ai.busy; onClicked: if(card.save()) card.ai.testConnection() }
    }
}
