pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasmoid

PlasmaExtras.Representation {
    id: full

    required property PlasmoidItem plasmoidItem

    Layout.minimumWidth: Kirigami.Units.gridUnit * 21
    Layout.minimumHeight: Kirigami.Units.gridUnit * 18
    Layout.preferredWidth: Kirigami.Units.gridUnit * 27
    // Sized for the denser rows. maximumHeight as well as preferredHeight: the
    // popup was ignoring the preferred value on its own and claiming height it
    // could not fill, leaving dead space under the last provider.
    Layout.preferredHeight: Kirigami.Units.gridUnit * 40
    Layout.maximumHeight: Kirigami.Units.gridUnit * 42

    collapseMarginsHint: true

    header: PlasmaExtras.PlasmoidHeading {
        id: heading
        leftPadding: full.plasmoidItem.inset
        rightPadding: full.plasmoidItem.inset
        topPadding: Math.round(Kirigami.Units.smallSpacing * 0.9)
        bottomPadding: Math.round(Kirigami.Units.smallSpacing * 0.8)

        background: Item {
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 1
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.08; color: full.plasmoidItem.line }
                    GradientStop { position: 0.92; color: full.plasmoidItem.line }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
        }

        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                spacing: Math.round(Kirigami.Units.smallSpacing * 0.8)

                Kirigami.Icon {
                    source: "speedometer"
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: implicitWidth
                    color: Kirigami.Theme.highlightColor
                }

                PlasmaComponents.Label {
                    text: i18n("AI Credits")
                    color: full.plasmoidItem.ink
                    font.weight: Font.Bold
                    font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.05)
                }
            }

            Rectangle {
                readonly property int crit: full.plasmoidItem.criticalCount || 0
                readonly property int warn: full.plasmoidItem.warningCount || 0
                readonly property int attn: full.plasmoidItem.attentionCount || 0

                visible: full.plasmoidItem.loaded && full.plasmoidItem.providers.length > 0
                implicitHeight: Math.round(healthLabel.implicitHeight + 4)
                implicitWidth: Math.round(healthLabel.implicitWidth + Kirigami.Units.smallSpacing * 1.6)
                radius: full.plasmoidItem.badgeRadius

                color: (crit > 0 || attn > 0)
                       ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.16)
                       : (warn > 0)
                       ? Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.16)
                       : Qt.rgba(Kirigami.Theme.positiveTextColor.r, Kirigami.Theme.positiveTextColor.g, Kirigami.Theme.positiveTextColor.b, 0.14)

                border.width: 1
                border.color: (crit > 0 || attn > 0)
                              ? Qt.rgba(Kirigami.Theme.negativeTextColor.r, Kirigami.Theme.negativeTextColor.g, Kirigami.Theme.negativeTextColor.b, 0.35)
                              : (warn > 0)
                              ? Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.35)
                              : Qt.rgba(Kirigami.Theme.positiveTextColor.r, Kirigami.Theme.positiveTextColor.g, Kirigami.Theme.positiveTextColor.b, 0.28)

                PlasmaComponents.Label {
                    id: healthLabel
                    anchors.centerIn: parent
                    text: {
                        if (parent.crit > 0)
                            return i18np("%1 critical", "%1 critical", parent.crit);
                        if (parent.attn > 0)
                            return i18np("%1 needs setup", "%1 need setup", parent.attn);
                        if (parent.warn > 0)
                            return i18np("%1 warning", "%1 warning", parent.warn);
                        return i18n("all normal");
                    }
                    color: (parent.crit > 0 || parent.attn > 0)
                           ? Kirigami.Theme.negativeTextColor
                           : (parent.warn > 0)
                           ? Kirigami.Theme.neutralTextColor
                           : Kirigami.Theme.positiveTextColor
                    font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.82)
                    font.weight: Font.DemiBold
                    font.capitalization: Font.AllUppercase
                }
            }

            Item { Layout.fillWidth: true }

            PlasmaComponents.Label {
                text: full.plasmoidItem.loaded
                      ? full.plasmoidItem.relativeTime(full.plasmoidItem.updatedAt) : ""
                color: full.plasmoidItem.inkSoft
                font: Kirigami.Theme.smallFont
            }

            PlasmaComponents.ToolButton {
                id: refreshBtn
                icon.name: "view-refresh"
                flat: true
                opacity: hovered ? 1 : 0.65
                text: i18n("Refresh now")
                display: PlasmaComponents.AbstractButton.IconOnly
                PlasmaComponents.ToolTip.text: text
                PlasmaComponents.ToolTip.visible: hovered
                PlasmaComponents.ToolTip.delay: Kirigami.Units.toolTipDelay
                enabled: !full.plasmoidItem.refreshing
                onClicked: full.plasmoidItem.refreshNow()

                RotationAnimation on rotation {
                    running: full.plasmoidItem.refreshing
                    loops: Animation.Infinite
                    from: 0
                    to: 360
                    duration: 900
                }
            }

            PlasmaComponents.ToolButton {
                icon.name: "configure"
                flat: true
                opacity: hovered ? 1 : 0.65
                text: i18n("Configure AI Credits")
                display: PlasmaComponents.AbstractButton.IconOnly
                PlasmaComponents.ToolTip.text: text
                PlasmaComponents.ToolTip.visible: hovered
                PlasmaComponents.ToolTip.delay: Kirigami.Units.toolTipDelay
                onClicked: Plasmoid.internalAction("configure").trigger()
            }
        }
    }

    PlasmaComponents.ScrollView {
        anchors.fill: parent

        PlasmaComponents.ScrollBar.horizontal.policy: PlasmaComponents.ScrollBar.AlwaysOff
        contentWidth: availableWidth

        contentItem: ListView {
            id: list
            model: full.plasmoidItem.providers
            spacing: Math.round(Kirigami.Units.smallSpacing * 1.5)
            clip: true
            reuseItems: true
            topMargin: Math.round(Kirigami.Units.smallSpacing * 1.25)
            bottomMargin: Math.round(Kirigami.Units.smallSpacing * 1.25)

            delegate: ProviderRow {
                required property var modelData
                required property int index
                provider: modelData
                owner: full.plasmoidItem
                showSeparator: false
                width: ListView.view.width
                visible: !Plasmoid.configuration.hideUnconfigured
                         || modelData.status !== "auth_needed"
                height: visible ? implicitHeight : 0
            }
        }
    }

    PlasmaExtras.PlaceholderMessage {
        anchors.centerIn: parent
        width: parent.width - Kirigami.Units.gridUnit * 4
        visible: full.plasmoidItem.providers.length === 0
        iconName: "view-refresh"
        text: i18n("No snapshot yet")
        explanation: full.plasmoidItem.loadError !== ""
                     ? full.plasmoidItem.loadError
                     : i18n("Run the collector once: aicredits poll")
    }

    footer: PlasmaExtras.PlasmoidHeading {
        id: footerBar
        position: PlasmaExtras.PlasmoidHeading.Position.Footer
        leftPadding: full.plasmoidItem.inset
        rightPadding: full.plasmoidItem.inset
        topPadding: Math.round(Kirigami.Units.smallSpacing * 0.8)
        bottomPadding: Math.round(Kirigami.Units.smallSpacing * 0.9)

        background: Item {
            Rectangle {
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: 1
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.08; color: full.plasmoidItem.line }
                    GradientStop { position: 0.92; color: full.plasmoidItem.line }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
        }
        visible: full.plasmoidItem.totals
                 && full.plasmoidItem.totals.monthly_usd !== undefined

        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: renewalContent.implicitHeight + Math.round(Kirigami.Units.smallSpacing * 1.2)
                radius: full.plasmoidItem.badgeRadius
                gradient: Gradient {
                    GradientStop {
                        position: 0.0
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.055)
                    }
                    GradientStop {
                        position: 1.0
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.025)
                    }
                }
                border.width: 1
                border.color: full.plasmoidItem.cardBorder

                Rectangle {
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    height: 1
                    radius: parent.radius
                    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.07)
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Plasmoid.internalAction("configure").trigger()

                    RowLayout {
                        id: renewalContent
                        anchors {
                            left: parent.left
                            right: parent.right
                            verticalCenter: parent.verticalCenter
                            leftMargin: Kirigami.Units.smallSpacing
                            rightMargin: Kirigami.Units.smallSpacing
                        }
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Icon {
                            source: "view-calendar"
                            implicitWidth: Kirigami.Units.iconSizes.small
                            implicitHeight: implicitWidth
                            color: Kirigami.Theme.highlightColor
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            PlasmaComponents.Label {
                                text: i18n("Next renewal").toUpperCase()
                                color: full.plasmoidItem.inkSoft
                                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.78)
                                font.letterSpacing: 0.8
                                font.capitalization: Font.AllUppercase
                            }
                            PlasmaComponents.Label {
                                text: {
                                    const totals = full.plasmoidItem.totals || ({});
                                    const next = totals.next_renewal;
                                    if (next)
                                        return i18n("%1 · %2", next.label,
                                                    full.plasmoidItem.displayDate(next.date));
                                    const count = totals.subscriptions_total || 0;
                                    return count ? i18n("Add dates for %1 subscriptions", count)
                                                 : i18n("None configured");
                                }
                                color: full.plasmoidItem.ink
                                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.95)
                                font.weight: Font.Medium
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: Math.round(Kirigami.Units.gridUnit * 7.5)
                implicitHeight: spendContent.implicitHeight + Math.round(Kirigami.Units.smallSpacing * 1.2)
                radius: full.plasmoidItem.badgeRadius
                gradient: Gradient {
                    GradientStop {
                        position: 0.0
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.055)
                    }
                    GradientStop {
                        position: 1.0
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.025)
                    }
                }
                border.width: 1
                border.color: full.plasmoidItem.cardBorder

                Rectangle {
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    height: 1
                    radius: parent.radius
                    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.07)
                }

                RowLayout {
                    id: spendContent
                    anchors {
                        fill: parent
                        leftMargin: Kirigami.Units.smallSpacing
                        rightMargin: Kirigami.Units.smallSpacing
                    }
                    spacing: Kirigami.Units.smallSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        PlasmaComponents.Label {
                            text: i18n("Per month").toUpperCase()
                            color: full.plasmoidItem.inkSoft
                            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.78)
                            font.letterSpacing: 0.8
                            font.capitalization: Font.AllUppercase
                            Layout.alignment: Qt.AlignRight
                        }
                        PlasmaComponents.Label {
                            text: {
                                const totals = full.plasmoidItem.totals || ({});
                                return "$" + (totals.monthly_usd || 0).toFixed(2);
                            }
                            color: full.plasmoidItem.ink
                            font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.15)
                            font.weight: Font.Bold
                            Layout.alignment: Qt.AlignRight
                        }
                    }
                }
            }
        }
    }
}
