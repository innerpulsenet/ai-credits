pragma ComponentBehavior: Bound

import QtQuick
import QtCore
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as Plasma5Support

QQC2.ScrollView {
    id: page
    clip: true
    contentWidth: availableWidth
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    readonly property string homeDir:
        String(StandardPaths.standardLocations(StandardPaths.HomeLocation)[0])
            .replace(/^file:\/\//, "")
    property string cfg_cliPath: "Documents/ai-credits/bin/aicredits"
    readonly property string cliPath: page.cfg_cliPath.startsWith("/")
                                      ? page.cfg_cliPath
                                      : page.homeDir + "/" + page.cfg_cliPath
    property bool busy: false
    property string resultText: ""

    readonly property var codexSources: [
        { value: "auto", label: i18n("Auto (ChatGPT session, then CLI)") },
        { value: "oauth", label: i18n("ChatGPT session only") },
        { value: "cli", label: i18n("Codex CLI only") }
    ]
    readonly property var grokSources: [
        { value: "auto", label: i18n("Auto (HTTP, then log)") },
        { value: "http", label: i18n("HTTP only") },
        { value: "cli", label: i18n("Grok CLI (starts the TUI)") }
    ]

    property int codexSourceIndex: 0
    property int grokSourceIndex: 0
    property bool codexExtra: true
    property bool claudeExtra: true
    property bool openrouterKey: true
    property bool deepseekKeySet: false
    property string deepseekKey: ""
    property string keyResultText: ""

    readonly property color glass: Qt.rgba(Kirigami.Theme.backgroundColor.r,
                                            Kirigami.Theme.backgroundColor.g,
                                            Kirigami.Theme.backgroundColor.b, 0.52)
    readonly property color glassRaised: Qt.rgba(Kirigami.Theme.textColor.r,
                                                  Kirigami.Theme.textColor.g,
                                                  Kirigami.Theme.textColor.b, 0.055)
    readonly property color glassHover: Qt.rgba(Kirigami.Theme.highlightColor.r,
                                                 Kirigami.Theme.highlightColor.g,
                                                 Kirigami.Theme.highlightColor.b, 0.10)
    readonly property color hairline: Qt.rgba(Kirigami.Theme.textColor.r,
                                               Kirigami.Theme.textColor.g,
                                               Kirigami.Theme.textColor.b, 0.13)
    readonly property int cardRadius: Math.round(Kirigami.Units.gridUnit * 0.65)

    component GlassCombo: QQC2.ComboBox {
        id: combo
        implicitHeight: Kirigami.Units.gridUnit * 2.25
        leftPadding: Kirigami.Units.largeSpacing
        rightPadding: Kirigami.Units.gridUnit * 2.2
        textRole: "label"
        valueRole: "value"
        contentItem: QQC2.Label {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: combo.leftPadding
            anchors.rightMargin: combo.rightPadding
            text: combo.displayText
            font: combo.font
            color: Kirigami.Theme.textColor
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Kirigami.Icon {
            anchors.right: combo.right
            anchors.rightMargin: Kirigami.Units.largeSpacing
            anchors.verticalCenter: combo.verticalCenter
            implicitWidth: Kirigami.Units.iconSizes.small
            implicitHeight: implicitWidth
            source: "arrow-down"
            color: combo.hovered ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
        }
        background: Rectangle {
            radius: Math.round(Kirigami.Units.gridUnit * 0.45)
            color: combo.activeFocus ? page.glassHover : page.glass
            border.width: combo.activeFocus ? 2 : 1
            border.color: combo.activeFocus ? Kirigami.Theme.highlightColor : page.hairline
        }
        delegate: QQC2.ItemDelegate {
            id: itemDel
            required property var modelData
            required property int index
            width: combo.width
            contentItem: QQC2.Label {
                text: itemDel.modelData.label
                color: itemDel.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                elide: Text.ElideRight
            }
            highlighted: combo.highlightedIndex === index
            background: Rectangle {
                color: itemDel.highlighted ? Kirigami.Theme.highlightColor : "transparent"
                radius: 4
            }
        }
        popup: QQC2.Popup {
            y: combo.height + 2
            width: combo.width
            implicitHeight: contentItem.implicitHeight + 8
            padding: 4
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
            }
            background: Rectangle {
                radius: Math.round(Kirigami.Units.gridUnit * 0.45)
                color: Kirigami.Theme.backgroundColor
                border.width: 1
                border.color: page.hairline
            }
        }
    }

    component GlassField: QQC2.TextField {
        leftPadding: Kirigami.Units.largeSpacing
        rightPadding: Kirigami.Units.largeSpacing
        implicitHeight: Kirigami.Units.gridUnit * 2.25
        background: Rectangle {
            radius: Math.round(Kirigami.Units.gridUnit * 0.45)
            color: parent.activeFocus ? page.glassHover : page.glass
            border.width: parent.activeFocus ? 2 : 1
            border.color: parent.activeFocus ? Kirigami.Theme.highlightColor : page.hairline
        }
    }

    function quote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function indexOfValue(items, value, fallback) {
        for (let i = 0; i < items.length; ++i) {
            if (items[i].value === value)
                return i
        }
        return fallback
    }

    function loadValues(text) {
        try {
            const providers = JSON.parse(text)
            page.codexSourceIndex = page.indexOfValue(page.codexSources, (providers.codex || {}).source, 0)
            page.grokSourceIndex = page.indexOfValue(page.grokSources, (providers.grok || {}).source, 0)
            page.codexExtra = (providers.codex || {}).show_extra !== false
            page.claudeExtra = (providers.claude || {}).show_extra !== false
            page.openrouterKey = (providers.openrouter || {}).fetch_key !== false
            page.resultText = ""
        } catch (error) {
            page.resultText = i18n("Could not read fetch-source configuration.")
        }
    }

    function saveValues() {
        const sets = [
            ["providers.codex.source", page.codexSources[page.codexSourceIndex].value],
            ["providers.codex.show_extra", page.codexExtra ? "true" : "false"],
            ["providers.grok.source", page.grokSources[page.grokSourceIndex].value],
            ["providers.claude.show_extra", page.claudeExtra ? "true" : "false"],
            ["providers.openrouter.fetch_key", page.openrouterKey ? "true" : "false"]
        ]
        const commands = sets.map(pair => page.quote(page.cliPath) + " config set " + pair[0] + " " + page.quote(pair[1]))
        commands.push("systemctl --user start aicredits.service")
        page.busy = true
        page.resultText = i18n("Saving…")
        writer.successText = i18n("Fetch sources saved. The popup will update shortly.")
        writer.failText = i18n("Could not save fetch sources.")
        writer.connectSource(commands.join(" && "))
    }

    function loadAuth(text) {
        page.deepseekKeySet = /(^|\n)\s*deepseek\s+set\s*(\n|$)/.test(text)
    }

    function saveDeepSeekKey() {
        const key = page.deepseekKey.trim()
        if (key === "") {
            page.keyResultText = i18n("Enter a DeepSeek API key first.")
            return
        }
        page.busy = true
        page.keyResultText = i18n("Saving…")
        writer.successText = i18n("DeepSeek key stored. The popup will update shortly.")
        writer.failText = i18n("Could not store the DeepSeek key.")
        writer.connectSource("printf %s " + page.quote(key) + " | "
                             + page.quote(page.cliPath) + " auth set deepseek"
                             + " && systemctl --user start aicredits.service")
        page.deepseekKey = ""
    }

    function clearDeepSeekKey() {
        page.busy = true
        page.keyResultText = i18n("Removing…")
        writer.successText = i18n("DeepSeek key removed.")
        writer.failText = i18n("Could not remove the DeepSeek key.")
        writer.connectSource(page.quote(page.cliPath) + " auth clear deepseek"
                             + " && systemctl --user start aicredits.service")
        page.deepseekKey = ""
    }

    Plasma5Support.DataSource {
        id: reader
        engine: "executable"
        connectedSources: [page.quote(page.cliPath) + " config get providers"]
        interval: 0
        onNewData: function(source, data) {
            disconnectSource(source)
            if (data["exit code"] === 0)
                page.loadValues(data["stdout"])
            else
                page.resultText = i18n("Could not run %1", page.cliPath)
        }
    }

    Plasma5Support.DataSource {
        id: authReader
        engine: "executable"
        connectedSources: [page.quote(page.cliPath) + " auth list"]
        interval: 0
        onNewData: function(source, data) {
            disconnectSource(source)
            if (data["exit code"] === 0)
                page.loadAuth(data["stdout"])
        }
    }

    Plasma5Support.DataSource {
        id: writer
        engine: "executable"
        connectedSources: []
        interval: 0
        property string successText: ""
        property string failText: ""
        onNewData: function(source, data) {
            disconnectSource(source)
            page.busy = false
            const ok = data["exit code"] === 0
            const msg = ok ? writer.successText : writer.failText
            if (writer.successText.indexOf("DeepSeek") !== -1)
                page.keyResultText = msg
            else
                page.resultText = msg
            if (ok)
                authReader.connectSource(page.quote(page.cliPath) + " auth list")
        }
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: intro.implicitHeight + Kirigami.Units.gridUnit * 1.6
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline
            RowLayout {
                id: intro
                anchors { fill: parent; margins: Kirigami.Units.gridUnit }
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: "network-connect"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: width
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: i18n("Fetch sources"); level: 2 }
                    QQC2.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.disabledTextColor
                        text: i18n("Prefer a vendor HTTP API when a local login already exists. CLI fallbacks stay available.")
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: fields.implicitHeight + Kirigami.Units.gridUnit * 1.5
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline
            ColumnLayout {
                id: fields
                anchors { fill: parent; margins: Math.round(Kirigami.Units.gridUnit * 0.75) }
                spacing: Kirigami.Units.largeSpacing
                Kirigami.FormLayout {
                    Layout.fillWidth: true
                    GlassCombo {
                        Kirigami.FormData.label: i18n("Codex:")
                        Layout.fillWidth: true
                        model: page.codexSources
                        currentIndex: page.codexSourceIndex
                        onActivated: page.codexSourceIndex = index
                    }
                    QQC2.CheckBox {
                        Kirigami.FormData.label: " "
                        text: i18n("Show extra Codex windows (Spark and similar)")
                        checked: page.codexExtra
                        onToggled: page.codexExtra = checked
                    }
                    GlassCombo {
                        Kirigami.FormData.label: i18n("SuperGrok:")
                        Layout.fillWidth: true
                        model: page.grokSources
                        currentIndex: page.grokSourceIndex
                        onActivated: page.grokSourceIndex = index
                    }
                    QQC2.CheckBox {
                        Kirigami.FormData.label: i18n("Claude:")
                        text: i18n("Show extra windows (Sonnet/Opus, Routines, Extra)")
                        checked: page.claudeExtra
                        onToggled: page.claudeExtra = checked
                    }
                    QQC2.CheckBox {
                        Kirigami.FormData.label: i18n("OpenRouter:")
                        text: i18n("Also fetch key spend and any spending cap")
                        checked: page.openrouterKey
                        onToggled: page.openrouterKey = checked
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: page.resultText
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.disabledTextColor
                    }
                    QQC2.Button {
                        text: i18n("Save")
                        enabled: !page.busy
                        onClicked: page.saveValues()
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: keyBody.implicitHeight + Kirigami.Units.gridUnit * 1.5
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline
            ColumnLayout {
                id: keyBody
                anchors { fill: parent; margins: Math.round(Kirigami.Units.gridUnit * 0.75) }
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Heading { text: i18n("API keys"); level: 3 }
                QQC2.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    color: Kirigami.Theme.disabledTextColor
                    text: i18n("Stored in the desktop keyring, not in the config file. Leave the field blank to keep the current key.")
                }

                Kirigami.FormLayout {
                    Layout.fillWidth: true
                    GlassField {
                        Kirigami.FormData.label: i18n("DeepSeek:")
                        Layout.fillWidth: true
                        echoMode: TextInput.Password
                        text: page.deepseekKey
                        onTextChanged: page.deepseekKey = text
                        placeholderText: page.deepseekKeySet
                                         ? i18n("Key stored — paste a new one to replace it")
                                         : i18n("Paste API key from platform.deepseek.com")
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: page.keyResultText !== ""
                              ? page.keyResultText
                              : (page.deepseekKeySet ? i18n("A DeepSeek key is stored.")
                                                     : i18n("No DeepSeek key stored."))
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.disabledTextColor
                    }
                    QQC2.Button {
                        text: i18n("Remove")
                        enabled: !page.busy && page.deepseekKeySet
                        onClicked: page.clearDeepSeekKey()
                    }
                    QQC2.Button {
                        text: i18n("Save key")
                        enabled: !page.busy
                        onClicked: page.saveDeepSeekKey()
                    }
                }
            }
        }
    }
}
