pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "severity.js" as Severity

/*
 * A quiet provider header followed by the usage windows.
 */
Item {
    id: row

    required property var provider
    required property var owner
    property bool showSeparator: false

    readonly property bool attention: Severity.needsAttention(provider.status)
    readonly property bool isImminentRenewal: !!(row.provider.renewal && row.provider.renewal.days_until <= 3)

    readonly property string planText: {
        const p = row.provider.plan || "";
        if (!p)
            return "";
        return p;
    }

    implicitHeight: cardBg.implicitHeight

    HoverHandler { id: hover }

    Rectangle {
        id: cardBg
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
            leftMargin: row.owner.inset
            rightMargin: row.owner.inset
        }
        implicitHeight: body.implicitHeight + Math.round(Kirigami.Units.smallSpacing * 2.4)
        radius: row.owner.radius

        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                       Kirigami.Theme.textColor.b, hover.hovered ? 0.045 : 0.025)
        border.width: 1
        border.color: row.owner.cardBorder

        ColumnLayout {
            id: body
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
                leftMargin: Math.round(Kirigami.Units.smallSpacing * 1.5)
                rightMargin: Math.round(Kirigami.Units.smallSpacing * 1.5)
                topMargin: Math.round(Kirigami.Units.smallSpacing * 1.25)
                bottomMargin: Math.round(Kirigami.Units.smallSpacing * 1.25)
            }
            spacing: Math.round(Kirigami.Units.smallSpacing * 1.25)

            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing

                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Layout.fillWidth: true

                    PlasmaComponents.Label {
                        text: row.provider.label
                        Layout.maximumWidth: Kirigami.Units.gridUnit * 10
                        color: row.owner.ink
                        font.weight: Font.DemiBold
                        font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.05)
                        elide: Text.ElideRight
                    }

                    Rectangle {
                        visible: row.planText !== ""
                        implicitHeight: planLabel.implicitHeight + 4
                        implicitWidth: Math.min(planLabel.implicitWidth,
                                                Kirigami.Units.gridUnit * 7) + 12
                        radius: 4
                        color: Qt.rgba(Kirigami.Theme.textColor.r,
                                       Kirigami.Theme.textColor.g,
                                       Kirigami.Theme.textColor.b, 0.06)
                        border.width: 1
                        border.color: row.owner.cardBorder

                        PlasmaComponents.Label {
                            id: planLabel
                            anchors.centerIn: parent
                            width: Math.min(implicitWidth, Kirigami.Units.gridUnit * 7)
                            text: row.planText.toUpperCase()
                            color: row.owner.inkSoft
                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.85)
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.6
                            elide: Text.ElideRight
                        }
                    }

                    PlasmaComponents.Label {
                        visible: row.attention
                        text: row.owner.statusLabel(row.provider.status)
                        color: Kirigami.Theme.neutralTextColor
                        font: Kirigami.Theme.smallFont
                    }

                    Item { Layout.fillWidth: true }
                }

                PlasmaComponents.ToolButton {
                    visible: !!row.provider.url
                    icon.name: "internet-services"
                    flat: true
                    opacity: hovered ? 1 : 0.45
                    display: PlasmaComponents.AbstractButton.IconOnly
                    text: i18n("Open dashboard")
                    PlasmaComponents.ToolTip.text: text
                    PlasmaComponents.ToolTip.visible: hovered
                    PlasmaComponents.ToolTip.delay: Kirigami.Units.toolTipDelay
                    Layout.alignment: Qt.AlignVCenter
                    onClicked: Qt.openUrlExternally(row.provider.url)
                }
            }

            Repeater {
                model: (row.provider.meters || []).slice().sort((a, b) => {
                    const key = m => String(m.label).replace(/Weekly/gi, "7d");
                    return key(a).localeCompare(key(b));
                })

                delegate: MeterBar {
                    required property var modelData
                    meter: modelData
                    stale: row.attention
                    owner: row.owner
                    warnPct: row.owner.warnPct
                    criticalPct: row.owner.criticalPct
                    Layout.fillWidth: true
                    Layout.topMargin: 3
                }
            }

            PlasmaComponents.Label {
                visible: text !== ""
                Layout.fillWidth: true
                Layout.topMargin: 3
                text: row.provider.message || ""
                color: row.owner.inkSoft
                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.92)
                wrapMode: Text.WordWrap
            }

            RowLayout {
                visible: !!row.provider.renewal
                Layout.fillWidth: true
                Layout.topMargin: 3
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: "view-calendar"
                    implicitWidth: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.95)
                    implicitHeight: implicitWidth
                    color: row.isImminentRenewal ? Kirigami.Theme.neutralTextColor : row.owner.inkSoft
                }

                PlasmaComponents.Label {
                    text: {
                        const renewal = row.provider.renewal;
                        if (!renewal)
                            return "";
                        const cost = renewal.cost_usd ? " · $" + renewal.cost_usd.toFixed(2) : "";
                        const cadence = renewal.cadence === "daily" ? i18n("/day")
                                        : renewal.cadence === "annual" || renewal.cadence === "yearly"
                                        ? i18n("/year") : renewal.cadence === "weekly"
                                        ? i18n("/week") : renewal.cadence === "quarterly"
                                        ? i18n("/quarter") : i18n("/month");
                        const when = renewal.days_until === 0 ? i18n("today")
                                   : renewal.days_until === 1 ? i18n("tomorrow")
                                   : i18n("in %1 days", renewal.days_until);
                        return i18n("Renews %1 (%2)", row.owner.displayDate(renewal.date), when)
                               + cost + (cost ? cadence : "");
                    }
                    color: row.isImminentRenewal ? Kirigami.Theme.neutralTextColor : row.owner.inkSoft
                    font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.90)
                    font.weight: row.isImminentRenewal ? Font.DemiBold : Font.Normal
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
        }
    }

}
