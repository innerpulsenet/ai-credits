pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "severity.js" as Severity

/*
 * One provider card. Elevated micro-surface with clear visual hierarchy,
 * pill badges, 6px capsule progress bars, and high-contrast typography.
 */
Item {
    id: row

    required property var provider
    required property var owner
    property bool showSeparator: false

    readonly property bool attention: Severity.needsAttention(provider.status)
    readonly property bool hasFigure: provider.worst_pct !== undefined && !row.attention
    readonly property string level: Severity.of(row.provider.worst_pct,
                                                row.owner.warnPct, row.owner.criticalPct)
    readonly property bool isCritical: hasFigure && row.provider.worst_pct >= row.owner.criticalPct
    readonly property bool isWarning: hasFigure && row.provider.worst_pct >= row.owner.warnPct && !row.isCritical
    readonly property bool isImminentRenewal: !!(row.provider.renewal && row.provider.renewal.days_until <= 3)

    readonly property string planText: {
        if (row.attention)
            return row.owner.statusLabel(row.provider.status);
        const p = row.provider.plan || "";
        if (!p)
            return "";
        // Suppress redundant plan tag if identical to provider name
        if (p.toLowerCase() === String(row.provider.label || "").toLowerCase())
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

        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: row.attention
                       ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.10)
                       : (row.isCritical
                          ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.08)
                          : (row.isWarning
                             ? Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.06)
                             : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, hover.hovered ? 0.075 : 0.048)))
            }
            GradientStop {
                position: 1.0
                color: row.attention
                       ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.04)
                       : (row.isCritical
                          ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.03)
                          : (row.isWarning
                             ? Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.02)
                             : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, hover.hovered ? 0.040 : 0.022)))
            }
        }

        border.width: 1
        border.color: row.attention ? Qt.rgba(Kirigami.Theme.negativeTextColor.r,
                                              Kirigami.Theme.negativeTextColor.g,
                                              Kirigami.Theme.negativeTextColor.b, 0.35)
                    : (row.isCritical ? Qt.rgba(Kirigami.Theme.negativeTextColor.r,
                                                Kirigami.Theme.negativeTextColor.g,
                                                Kirigami.Theme.negativeTextColor.b, 0.28)
                    : (row.isWarning ? Qt.rgba(Kirigami.Theme.neutralTextColor.r,
                                               Kirigami.Theme.neutralTextColor.g,
                                               Kirigami.Theme.neutralTextColor.b, 0.24)
                    : (hover.hovered ? row.owner.cardBorderHover : row.owner.cardBorder)))

        Behavior on border.color { ColorAnimation { duration: Kirigami.Units.shortDuration } }

        // Subtle 1px specular light chamfer on the top edge of the card
        Rectangle {
            id: topHighlight
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
                leftMargin: 1
                rightMargin: 1
            }
            height: 1
            radius: parent.radius
            color: row.attention
                   ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.28)
                   : (row.isCritical
                      ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.22)
                      : (row.isWarning
                         ? Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.18)
                         : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, hover.hovered ? 0.13 : 0.075)))
        }

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
                        color: row.owner.ink
                        font.weight: Font.DemiBold
                        font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.05)
                        elide: Text.ElideRight
                    }

                    Rectangle {
                        visible: row.planText !== ""
                        implicitHeight: Math.round(planLabel.implicitHeight + 4)
                        implicitWidth: Math.round(planLabel.implicitWidth + Kirigami.Units.smallSpacing * 1.6)
                        radius: row.owner.badgeRadius
                        gradient: Gradient {
                            GradientStop {
                                position: 0.0
                                color: row.attention
                                       ? Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.20)
                                       : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.09)
                            }
                            GradientStop {
                                position: 1.0
                                color: row.attention
                                       ? Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.12)
                                       : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.05)
                            }
                        }
                        border.width: 1
                        border.color: row.attention ? Qt.rgba(Kirigami.Theme.neutralTextColor.r,
                                                              Kirigami.Theme.neutralTextColor.g,
                                                              Kirigami.Theme.neutralTextColor.b, 0.35)
                                                    : row.owner.badgeBorder

                        PlasmaComponents.Label {
                            id: planLabel
                            anchors.centerIn: parent
                            text: row.planText.toUpperCase()
                            color: row.attention ? Kirigami.Theme.neutralTextColor : row.owner.inkSoft
                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.82)
                            font.letterSpacing: 0.8
                            font.weight: Font.DemiBold
                            font.capitalization: Font.AllUppercase
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                ColumnLayout {
                    spacing: 1
                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                    Layout.preferredWidth: Math.round(row.owner.figureSize * 3.2)

                    RowLayout {
                        spacing: 1
                        Layout.alignment: Qt.AlignRight

                        PlasmaComponents.Label {
                            visible: row.hasFigure
                            text: Math.round(row.provider.worst_pct || 0)
                            color: row.owner.usageColor(row.provider.worst_pct)
                            font.pixelSize: row.owner.figureSize
                            font.weight: Font.Bold
                            font.letterSpacing: -0.5
                        }

                        PlasmaComponents.Label {
                            visible: row.hasFigure
                            text: "%"
                            color: row.owner.usageColor(row.provider.worst_pct)
                            font.pixelSize: Math.round(row.owner.figureSize * 0.52)
                            font.weight: Font.DemiBold
                            Layout.alignment: Qt.AlignBottom
                            Layout.bottomMargin: Math.round(row.owner.figureSize * 0.12)
                        }

                        PlasmaComponents.Label {
                            visible: !row.hasFigure
                            text: row.spendFigure()
                            color: row.attention ? row.owner.inkSoft : row.owner.ink
                            font.pixelSize: Math.round(row.owner.figureSize * 0.65)
                            font.weight: Font.DemiBold
                        }
                    }

                    RowLayout {
                        spacing: Kirigami.Units.smallSpacing
                        Layout.alignment: Qt.AlignRight

                        PlasmaComponents.Label {
                            visible: row.hasFigure && text !== ""
                            text: (row.provider.worst_label || "").toUpperCase()
                            color: row.owner.inkSoft
                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.80)
                            font.letterSpacing: 0.6
                            font.capitalization: Font.AllUppercase
                        }

                        Sparkline {
                            points: row.provider.spark || []
                            strokeColor: row.owner.usageColor(row.provider.worst_pct)
                            implicitWidth: Kirigami.Units.gridUnit * 2.8
                            implicitHeight: Math.round(Kirigami.Units.gridUnit * 0.72)
                        }
                    }
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
                model: row.provider.meters || []

                delegate: MeterBar {
                    required property var modelData
                    meter: modelData
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

    function spendFigure() {
        for (const meter of (row.provider.meters || []))
            if (meter.amount_usd !== undefined)
                return "$" + Math.round(meter.amount_usd);
        return row.attention ? "—" : "";
    }
}
