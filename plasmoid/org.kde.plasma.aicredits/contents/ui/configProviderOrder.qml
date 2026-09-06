pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "providerOrder.js" as ProviderOrder

QQC2.ScrollView {
    id: page
    contentWidth: availableWidth
    clip: true
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    property string cfg_providerOrder: ""
    readonly property var orderedProviders: ProviderOrder.sorted(ProviderOrder.catalog(), cfg_providerOrder)

    function moveProvider(index, offset) {
        const providers = page.orderedProviders.slice();
        const target = index + offset;
        if (target < 0 || target >= providers.length)
            return;
        const item = providers.splice(index, 1)[0];
        providers.splice(target, 0, item);
        page.cfg_providerOrder = providers.map(p => p.id).join(",");
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        Kirigami.Heading { text: i18n("Provider order"); level: 2 }
        QQC2.Label {
            Layout.fillWidth: true
            text: i18n("Move providers up or down to arrange the popup. Hidden providers keep their position for when they are shown again.")
            wrapMode: Text.WordWrap
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            Repeater {
                model: page.orderedProviders
                delegate: RowLayout {
                    id: providerRow
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    QQC2.Label {
                        text: providerRow.modelData.label
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    QQC2.ToolButton {
                        icon.name: "go-up"
                        text: i18n("Up")
                        Accessible.name: i18n("Move %1 up", providerRow.modelData.label)
                        display: QQC2.AbstractButton.TextBesideIcon
                        enabled: providerRow.index > 0
                        onClicked: page.moveProvider(providerRow.index, -1)
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.text: text
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    }
                    QQC2.ToolButton {
                        icon.name: "go-down"
                        text: i18n("Down")
                        Accessible.name: i18n("Move %1 down", providerRow.modelData.label)
                        display: QQC2.AbstractButton.TextBesideIcon
                        enabled: providerRow.index < page.orderedProviders.length - 1
                        onClicked: page.moveProvider(providerRow.index, 1)
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.text: text
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    }
                }
            }
        }

        QQC2.Button {
            text: i18n("Reset to alphabetical order")
            enabled: page.cfg_providerOrder !== ""
            onClicked: page.cfg_providerOrder = ""
        }
        Item { Layout.preferredHeight: Kirigami.Units.smallSpacing }
    }
}
