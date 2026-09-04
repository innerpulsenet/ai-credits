pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "severity.js" as Severity

/*
 * One provider. The figure you actually care about is set large and right
 * aligned, so eight providers scan as a single column of numbers; everything
 * else is deliberately quieter than it.
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

    implicitHeight: body.implicitHeight

    HoverHandler { id: hover }

    Rectangle {
        anchors {
            fill: body
            leftMargin: -Math.round(Kirigami.Units.smallSpacing * 1.5)
            rightMargin: -Math.round(Kirigami.Units.smallSpacing * 1.5)
            topMargin: -Kirigami.Units.smallSpacing
            bottomMargin: -Kirigami.Units.smallSpacing
        }
        radius: row.owner.radius
        color: hover.hovered ? row.owner.hoverColor : "transparent"
        Behavior on color {
            ColorAnimation { duration: Kirigami.Units.shortDuration }
        }
    }

    function spendFigure() {
        for (const meter of (row.provider.meters || []))
            if (meter.amount_usd !== undefined)
                return "$" + Math.round(meter.amount_usd);
        return row.attention ? "—" : "";
    }

    // The indent lives here, not on the delegate. Inside a delegate compiled
    // under ComponentBehavior: Bound, a property read through the typed
    // `PlasmoidItem` is resolved against the C++ type, so a custom property
    // like `inset` comes back undefined and silently indents by zero. `owner`
    // is untyped, so it resolves dynamically and works.
    ColumnLayout {
        id: body

        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
            leftMargin: row.owner.inset
            rightMargin: row.owner.inset
        }
        spacing: 1

        Rectangle {
            visible: row.showSeparator
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.bottomMargin: Math.round(Kirigami.Units.largeSpacing * 0.8)
            color: row.owner.line
        }

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
                    elide: Text.ElideRight
                }

                PlasmaComponents.Label {
                    visible: text !== ""
                    // Plan tier, or why this row has no number — set beside the
                    // name rather than beneath it, which is a whole text line
                    // saved on every provider.
                    text: (row.attention ? row.owner.statusLabel(row.provider.status)
                                         : (row.provider.plan || "")).toUpperCase()
                    color: row.attention ? Kirigami.Theme.neutralTextColor : row.owner.inkSoft
                    font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.88)
                    font.letterSpacing: 1.1
                    font.capitalization: Font.AllUppercase
                    elide: Text.ElideRight
                    Layout.maximumWidth: implicitWidth
                }

                // An explicit spacer, not fillWidth on the plan chip: that chip
                // is invisible on providers with no plan, and an invisible item
                // fills nothing, which left their figures stranded mid-row
                // instead of pushed to the right edge.
                Item { Layout.fillWidth: true }
            }

            ColumnLayout {
                spacing: 1
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                // A fixed column width, so every figure ends on the same edge
                // whether it reads 7%, 61% or 100%.
                Layout.preferredWidth: Math.round(row.owner.figureSize * 2.6)

                RowLayout {
                    spacing: 1
                    Layout.alignment: Qt.AlignRight

                    PlasmaComponents.Label {
                        visible: row.hasFigure
                        text: Math.round(row.provider.worst_pct || 0)
                        color: row.owner.usageColor(row.provider.worst_pct)
                        font.pixelSize: row.owner.figureSize
                        font.weight: Font.DemiBold
                        // Tight tracking on display type, the way large
                        // numerals want.
                        font.letterSpacing: -0.5
                    }

                    PlasmaComponents.Label {
                        visible: row.hasFigure
                        text: "%"
                        color: row.owner.inkSoft
                        font.pixelSize: Math.round(row.owner.figureSize * 0.5)
                        Layout.alignment: Qt.AlignBottom
                        Layout.bottomMargin: Math.round(row.owner.figureSize * 0.13)
                    }

                    PlasmaComponents.Label {
                        // No percentage to show: say what there is instead.
                        visible: !row.hasFigure
                        text: row.spendFigure()
                        color: row.attention ? row.owner.inkSoft : row.owner.ink
                        font.pixelSize: Math.round(row.owner.figureSize * 0.62)
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
                        font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.82)
                        font.letterSpacing: 0.8
                        font.capitalization: Font.AllUppercase
                    }

                    Sparkline {
                        points: row.provider.spark || []
                        strokeColor: row.owner.inkSoft
                        implicitWidth: Kirigami.Units.gridUnit * 2.5
                        implicitHeight: Math.round(Kirigami.Units.gridUnit * 0.6)
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
                Layout.topMargin: Math.round(Kirigami.Units.smallSpacing * 0.75)
            }
        }

        PlasmaComponents.Label {
            visible: text !== ""
            Layout.fillWidth: true
            Layout.topMargin: 2
            text: row.provider.message || ""
            color: row.owner.inkSoft
            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.92)
            wrapMode: Text.WordWrap
        }

        PlasmaComponents.Label {
            visible: !!row.provider.renewal
            Layout.fillWidth: true
            text: {
                const renewal = row.provider.renewal;
                if (!renewal)
                    return "";
                const cost = renewal.cost_usd ? " · $" + renewal.cost_usd.toFixed(2) : "";
                const cadence = renewal.cadence === "annual" || renewal.cadence === "yearly"
                                ? i18n("/year") : renewal.cadence === "weekly"
                                ? i18n("/week") : renewal.cadence === "quarterly"
                                ? i18n("/quarter") : i18n("/month");
                const when = renewal.days_until === 0 ? i18n("today")
                           : renewal.days_until === 1 ? i18n("tomorrow")
                           : i18n("in %1 days", renewal.days_until);
                return i18n("Renews %1 (%2)", row.owner.displayDate(renewal.date), when)
                       + cost + (cost ? cadence : "");
            }
            color: row.owner.inkSoft
            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.92)
        }
    }
}
