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

            PlasmaComponents.Label {
                visible: full.plasmoidItem.attentionCount > 0
                text: i18n("%1 need attention", full.plasmoidItem.attentionCount)
                color: Kirigami.Theme.neutralTextColor
                font: Kirigami.Theme.smallFont
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
            PlasmaComponents.Label {
                Layout.fillWidth: true
                text: {
                    const next = (full.plasmoidItem.totals || {}).next_renewal;
                    return next ? i18n("Next renewal: %1 · %2", next.label,
                                        full.plasmoidItem.displayDate(next.date)) : "";
                }
                font: Kirigami.Theme.smallFont
                color: full.plasmoidItem.inkSoft
                elide: Text.ElideRight
            }
            PlasmaComponents.Label {
                text: i18n("$%1/month", ((full.plasmoidItem.totals || {}).monthly_usd || 0).toFixed(2))
                font: Kirigami.Theme.smallFont
                color: full.plasmoidItem.inkSoft
            }
        }
    }
}
