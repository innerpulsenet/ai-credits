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
    Layout.preferredHeight: Kirigami.Units.gridUnit * 38
    Layout.maximumHeight: Kirigami.Units.gridUnit * 38

    collapseMarginsHint: true

    header: PlasmaExtras.PlasmoidHeading {
        id: heading
        leftPadding: full.plasmoidItem.inset
        rightPadding: full.plasmoidItem.inset
        topPadding: Math.round(Kirigami.Units.smallSpacing * 0.75)
        bottomPadding: Math.round(Kirigami.Units.smallSpacing * 0.75)

        // No filled band: the heading's square-cornered background fought the
        // popup's rounded frame at the top edge. A hairline does the same
        // separating job and lets the pane read as one surface.
        background: Item {
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 1
                color: full.plasmoidItem.line
            }
        }

        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents.Label {
                // Eyebrow rather than a heading: the numbers below are the
                // loudest thing in the popup, and the title should not compete.
                text: i18n("AI Credits").toUpperCase()
                color: full.plasmoidItem.inkSoft
                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.95)
                font.letterSpacing: 2.2
                font.capitalization: Font.AllUppercase
            }

            Item { Layout.fillWidth: true }

            PlasmaComponents.Label {
                text: full.plasmoidItem.loaded
                      ? full.plasmoidItem.relativeTime(full.plasmoidItem.updatedAt) : ""
                color: full.plasmoidItem.inkSoft
                font: Kirigami.Theme.smallFont
            }

            PlasmaComponents.ToolButton {
                icon.name: "view-refresh"
                flat: true
                opacity: hovered ? 1 : 0.55
                text: i18n("Refresh now")
                display: PlasmaComponents.AbstractButton.IconOnly
                PlasmaComponents.ToolTip.text: text
                PlasmaComponents.ToolTip.visible: hovered
                PlasmaComponents.ToolTip.delay: Kirigami.Units.toolTipDelay
                onClicked: full.plasmoidItem.refreshNow()
            }
        }
    }

    PlasmaComponents.ScrollView {
        // Anchored rather than assigned to contentItem: as contentItem, the
        // delegate's width (derived from the view) feeds back into the
        // Representation's implicit width and loops. The margins keep the list
        // out from under the header and footer, which is the only thing
        // contentItem was buying.
        anchors {
            fill: parent
            topMargin: full.header ? full.header.height : 0
            bottomMargin: (full.footer && full.footer.visible) ? full.footer.height : 0
        }

        // Without pinning the horizontal bar off, the view's implicit width
        // feeds back into the popup's — QTBUG-83890, same workaround the
        // stock Plasma widgets use.
        PlasmaComponents.ScrollBar.horizontal.policy: PlasmaComponents.ScrollBar.AlwaysOff
        contentWidth: availableWidth

        contentItem: ListView {
            id: list
            model: full.plasmoidItem.providers
            spacing: Kirigami.Units.largeSpacing
            clip: true
            reuseItems: true
            topMargin: Math.round(Kirigami.Units.largeSpacing * 1.25)
            bottomMargin: Kirigami.Units.largeSpacing

            delegate: ProviderRow {
                required property var modelData
                required property int index
                provider: modelData
                owner: full.plasmoidItem
                showSeparator: index > 0
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
        topPadding: Math.round(Kirigami.Units.smallSpacing * 1.25)
        bottomPadding: Math.round(Kirigami.Units.smallSpacing * 1.25)

        background: Item {
            Rectangle {
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: 1
                color: full.plasmoidItem.line
            }
        }
        visible: full.plasmoidItem.totals
                 && full.plasmoidItem.totals.monthly_usd !== undefined

        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing

            ColumnLayout {
                spacing: 0
                Layout.fillWidth: true
                Layout.preferredWidth: 1

                PlasmaComponents.Label {
                    text: i18n("Next renewal").toUpperCase()
                    color: full.plasmoidItem.inkSoft
                    font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.9)
                    font.letterSpacing: 1.1
                    font.capitalization: Font.AllUppercase
                }
                PlasmaComponents.Label {
                    text: {
                        const totals = full.plasmoidItem.totals || ({});
                        const next = totals.next_renewal;
                        return next ? i18n("%1 · %2", next.label, next.date)
                                    : i18n("none configured");
                    }
                    color: full.plasmoidItem.ink
                    font: Kirigami.Theme.smallFont
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            ColumnLayout {
                spacing: 0
                Layout.alignment: Qt.AlignRight

                PlasmaComponents.Label {
                    text: i18n("Per month").toUpperCase()
                    color: full.plasmoidItem.inkSoft
                    font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.9)
                    font.letterSpacing: 1.1
                    font.capitalization: Font.AllUppercase
                    Layout.alignment: Qt.AlignRight
                }
                PlasmaComponents.Label {
                    text: {
                        const totals = full.plasmoidItem.totals || ({});
                        return "$" + (totals.monthly_usd || 0).toFixed(2);
                    }
                    color: full.plasmoidItem.ink
                    font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.1)
                    font.weight: Font.DemiBold
                    Layout.alignment: Qt.AlignRight
                }
            }
        }
    }
}
