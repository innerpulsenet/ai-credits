pragma ComponentBehavior: Bound

import QtQuick
import QtCore
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as Plasma5Support
import "providerOrder.js" as ProviderOrder

QQC2.ScrollView {
    id: page
    contentWidth: availableWidth
    clip: true
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    property string cfg_providerOrder: ""
    property string cfg_cliPath: "Documents/ai-credits/bin/aicredits"
    readonly property string homeDir:
        String(StandardPaths.standardLocations(StandardPaths.HomeLocation)[0])
            .replace(/^file:\/\//, "")
    readonly property string cliPath: page.cfg_cliPath.startsWith("/")
                                      ? page.cfg_cliPath
                                      : page.homeDir + "/" + page.cfg_cliPath
    readonly property var orderedProviders: ProviderOrder.sorted(ProviderOrder.catalog(), cfg_providerOrder)

    property int selectedIndex: 0
    property var enabledMap: ({})
    property bool busy: false
    property string resultText: ""

    readonly property var selectedProvider: {
        const list = page.orderedProviders;
        if (page.selectedIndex < 0 || page.selectedIndex >= list.length)
            return null;
        return list[page.selectedIndex];
    }

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

    function quote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function isEnabled(id) {
        return page.enabledMap[id] !== false;
    }

    function moveSelected(offset) {
        const providers = page.orderedProviders.slice();
        const index = page.selectedIndex;
        const target = index + offset;
        if (index < 0 || target < 0 || target >= providers.length)
            return;
        const item = providers.splice(index, 1)[0];
        providers.splice(target, 0, item);
        page.cfg_providerOrder = providers.map(p => p.id).join(",");
        page.selectedIndex = target;
    }

    function loadValues(text) {
        try {
            const providers = JSON.parse(text);
            const map = {};
            for (const item of ProviderOrder.catalog())
                map[item.id] = (providers[item.id] || {}).enabled !== false;
            page.enabledMap = map;
            page.resultText = "";
        } catch (error) {
            page.resultText = i18n("Could not read provider configuration.");
        }
    }

    function setEnabled(id, on) {
        const next = Object.assign({}, page.enabledMap);
        next[id] = on;
        page.enabledMap = next;
        page.busy = true;
        page.resultText = i18n("Saving…");
        const shown = on ? i18n("%1 will show in the popup.", page.labelFor(id))
                         : i18n("%1 will be hidden from the popup.", page.labelFor(id));
        writer.successText = shown + " " + i18n("The list will update shortly.");
        writer.connectSource(page.quote(page.cliPath)
                             + " config set providers." + id + ".enabled " + (on ? "true" : "false")
                             + " && systemctl --user start aicredits.service");
    }

    function labelFor(id) {
        for (const item of ProviderOrder.catalog()) {
            if (item.id === id)
                return item.label;
        }
        return id;
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
        id: writer
        engine: "executable"
        connectedSources: []
        interval: 0
        property string successText: ""
        onNewData: function(source, data) {
            disconnectSource(source)
            page.busy = false
            page.resultText = data["exit code"] === 0
                              ? writer.successText
                              : i18n("Could not save provider visibility.")
        }
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: intro.implicitHeight + Kirigami.Units.gridUnit * 2
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline

            Rectangle {
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                width: Math.round(Kirigami.Units.smallSpacing * 0.65)
                radius: parent.radius
                color: Kirigami.Theme.highlightColor
                opacity: 0.8
            }

            RowLayout {
                id: intro
                anchors {
                    fill: parent
                    margins: Kirigami.Units.gridUnit
                    leftMargin: Kirigami.Units.gridUnit * 1.25
                }
                spacing: Kirigami.Units.largeSpacing

                Rectangle {
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: width
                    radius: width / 2
                    color: page.glassHover
                    Kirigami.Icon {
                        anchors.centerIn: parent
                        width: Kirigami.Units.iconSizes.smallMedium
                        height: width
                        source: "view-sort-ascending"
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: i18n("Providers"); level: 2 }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: i18n("Select a provider, then use the buttons below to move it. The switch hides a provider you are not keeping — it stays in this list so you can turn it back on.")
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.disabledTextColor
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: listBody.implicitHeight + Kirigami.Units.gridUnit * 1.5
            radius: page.cardRadius
            color: page.glassRaised
            border.width: 1
            border.color: page.hairline

            ColumnLayout {
                id: listBody
                anchors { fill: parent; margins: Math.round(Kirigami.Units.gridUnit * 0.75) }
                spacing: Kirigami.Units.smallSpacing

                Repeater {
                    model: page.orderedProviders
                    delegate: Rectangle {
                        id: providerRow
                        required property var modelData
                        required property int index
                        readonly property bool selected: page.selectedIndex === index
                        readonly property bool on: page.isEnabled(modelData.id)
                        readonly property color accent: modelData.color

                        Layout.fillWidth: true
                        implicitHeight: Kirigami.Units.gridUnit * 2.55
                        radius: Math.round(Kirigami.Units.gridUnit * 0.4)
                        color: providerRow.selected ? page.glassHover
                               : rowHover.hovered ? Qt.rgba(Kirigami.Theme.textColor.r,
                                                            Kirigami.Theme.textColor.g,
                                                            Kirigami.Theme.textColor.b, 0.04)
                               : "transparent"
                        border.width: providerRow.selected ? 1 : 0
                        border.color: Qt.rgba(Kirigami.Theme.highlightColor.r,
                                              Kirigami.Theme.highlightColor.g,
                                              Kirigami.Theme.highlightColor.b, 0.4)
                        Behavior on color { ColorAnimation { duration: Kirigami.Units.shortDuration } }

                        HoverHandler { id: rowHover }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Kirigami.Units.smallSpacing
                            anchors.rightMargin: Kirigami.Units.smallSpacing
                            spacing: Kirigami.Units.smallSpacing

                            MouseArea {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                onClicked: page.selectedIndex = providerRow.index

                                RowLayout {
                                    anchors.fill: parent
                                    spacing: Kirigami.Units.smallSpacing

                                    QQC2.Label {
                                        text: String(providerRow.index + 1)
                                        color: Kirigami.Theme.disabledTextColor
                                        font: Kirigami.Theme.smallFont
                                        Layout.preferredWidth: Kirigami.Units.gridUnit
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    Rectangle {
                                        Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                                        Layout.preferredHeight: width
                                        radius: width / 2
                                        color: Qt.rgba(providerRow.accent.r, providerRow.accent.g,
                                                       providerRow.accent.b, providerRow.on ? 0.22 : 0.08)
                                        border.width: 1
                                        border.color: Qt.rgba(providerRow.accent.r, providerRow.accent.g,
                                                              providerRow.accent.b, providerRow.on ? 0.7 : 0.25)
                                        QQC2.Label {
                                            anchors.centerIn: parent
                                            text: providerRow.modelData.glyph
                                            color: providerRow.on ? providerRow.accent : Kirigami.Theme.disabledTextColor
                                            font.weight: Font.Bold
                                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.9)
                                        }
                                    }

                                    QQC2.Label {
                                        text: providerRow.modelData.label
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                        font.weight: providerRow.selected ? Font.DemiBold : Font.Normal
                                        color: providerRow.on ? Kirigami.Theme.textColor : Kirigami.Theme.disabledTextColor
                                    }

                                    QQC2.Label {
                                        visible: !providerRow.on
                                        text: i18n("Hidden")
                                        color: Kirigami.Theme.disabledTextColor
                                        font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.85)
                                        font.letterSpacing: 0.4
                                    }
                                }
                            }

                            QQC2.Switch {
                                checked: providerRow.on
                                enabled: !page.busy
                                Accessible.name: providerRow.on
                                                 ? i18n("Hide %1", providerRow.modelData.label)
                                                 : i18n("Show %1", providerRow.modelData.label)
                                onToggled: page.setEnabled(providerRow.modelData.id, checked)
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    implicitHeight: 1
                    color: page.hairline
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    spacing: Kirigami.Units.smallSpacing

                    QQC2.Label {
                        Layout.fillWidth: true
                        text: page.selectedProvider
                              ? i18n("Moving %1", page.selectedProvider.label)
                              : i18n("Select a provider to reorder")
                        color: Kirigami.Theme.disabledTextColor
                        elide: Text.ElideRight
                    }

                    Rectangle {
                        implicitHeight: moveButtons.implicitHeight
                        implicitWidth: moveButtons.implicitWidth
                        radius: Math.round(Kirigami.Units.gridUnit * 0.4)
                        color: page.glass
                        border.width: 1
                        border.color: page.hairline

                        RowLayout {
                            id: moveButtons
                            anchors.centerIn: parent
                            spacing: 0

                            QQC2.ToolButton {
                                icon.name: "go-top"
                                display: QQC2.AbstractButton.IconOnly
                                text: i18n("Move to top")
                                Accessible.name: text
                                enabled: page.selectedIndex > 0
                                onClicked: page.moveSelected(-page.selectedIndex)
                                QQC2.ToolTip.visible: hovered
                                QQC2.ToolTip.text: text
                                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                            }
                            QQC2.ToolButton {
                                icon.name: "go-up"
                                display: QQC2.AbstractButton.IconOnly
                                text: i18n("Move up")
                                Accessible.name: text
                                enabled: page.selectedIndex > 0
                                onClicked: page.moveSelected(-1)
                                QQC2.ToolTip.visible: hovered
                                QQC2.ToolTip.text: text
                                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                            }
                            QQC2.ToolButton {
                                icon.name: "go-down"
                                display: QQC2.AbstractButton.IconOnly
                                text: i18n("Move down")
                                Accessible.name: text
                                enabled: page.selectedIndex >= 0
                                          && page.selectedIndex < page.orderedProviders.length - 1
                                onClicked: page.moveSelected(1)
                                QQC2.ToolTip.visible: hovered
                                QQC2.ToolTip.text: text
                                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                            }
                            QQC2.ToolButton {
                                icon.name: "go-bottom"
                                display: QQC2.AbstractButton.IconOnly
                                text: i18n("Move to bottom")
                                Accessible.name: text
                                enabled: page.selectedIndex >= 0
                                          && page.selectedIndex < page.orderedProviders.length - 1
                                onClicked: page.moveSelected(page.orderedProviders.length - 1 - page.selectedIndex)
                                QQC2.ToolTip.visible: hovered
                                QQC2.ToolTip.text: text
                                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                            }
                        }
                    }
                }
            }
        }

        Kirigami.InlineMessage {
            visible: page.resultText !== ""
            text: page.resultText
            type: Kirigami.MessageType.Information
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            QQC2.Button {
                text: i18n("Reset to alphabetical order")
                enabled: page.cfg_providerOrder !== ""
                onClicked: {
                    page.cfg_providerOrder = "";
                    page.selectedIndex = 0;
                }
            }
            Item { Layout.fillWidth: true }
        }

        Item { Layout.preferredHeight: Kirigami.Units.smallSpacing }
    }
}
